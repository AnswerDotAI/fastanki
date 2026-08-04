import os, sys, time, subprocess, tempfile, shutil, threading
import pytest, httpx
from pathlib import Path
from fastanki.collection import Collection
from fastanki.syncer import SyncServer, SanityCheckFailed, start_sync_server
from fastanki.media import MediaSanityFailed

from anki.collection import Collection as AnkiCollection

pytestmark = pytest.mark.timeout(120)

@pytest.fixture
def server():
    base = tempfile.mkdtemp()
    proc, ep = start_sync_server(base)
    try: yield ep
    finally:
        proc.terminate()
        try: proc.wait(timeout=10)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait()
        shutil.rmtree(base, ignore_errors=True)

def test_round_trip(server, tmp_path):
    ep = server
    col = Collection.open(tmp_path/'ours'/'collection.anki2')
    n1 = col.add(Front='syncme', Back='please', tags='wire', deck='Sync::Deep')
    ncz = col.add(model='Cloze', Text='{{c1::first}} {{c2::second}}')

    # bad auth is rejected
    with pytest.raises(httpx.HTTPStatusError): col.sync_collection(SyncServer(ep, hkey='bad'))

    # first sync of fresh client+server is a full one
    res = col.sync(user='tester', passw='s3kret', endpoint=ep, upload=True)
    assert res == 'full sync'
    assert col.sync() == 'noChanges'

    # empty-local guard: an empty collection may not clobber a non-empty server
    empty = Collection.open(tmp_path/'empty'/'collection.anki2')
    with pytest.raises(ValueError, match='Refusing'):
        empty.sync(user='tester', passw='s3kret', endpoint=ep, upload=True)
    empty.close()

    # anki as second client: full download, then verify our upload arrived intact
    (tmp_path/'second').mkdir()
    oc = AnkiCollection(str(tmp_path/'second'/'collection.anki2'))
    auth = oc.sync_login('tester', 's3kret', endpoint=ep)
    st = oc.sync_collection(auth, sync_media=False)
    oc.close_for_full_sync()
    oc.full_upload_or_download(auth=auth, server_usn=st.server_media_usn, upload=False)
    oc.reopen(after_full_sync=True)
    assert sorted(oc.find_notes('')) == sorted([n1.id, ncz.id])
    assert oc.find_notes('tag:wire') == [n1.id]
    assert oc.find_notes('deck:Sync::Deep') == [n1.id]
    assert oc.get_note(ncz.id)['Text'] == '{{c1::first}} {{c2::second}}'

    # oracle makes changes: new note in new deck, an edit, a deletion; delta-syncs up
    theirs = oc.new_note(oc.models.by_name('Basic'))
    theirs['Front'] = 'from the other side'
    oc.add_note(theirs, oc.decks.add_normal_deck_with_name('Oracle').id)
    on = oc.get_note(n1.id)
    on['Back'] = 'edited remotely'
    oc.update_note(on)
    oc.remove_notes([ncz.id])
    st = oc.sync_collection(auth, sync_media=False)
    assert st.required == st.NO_CHANGES

    # delta sync brings all three changes to us (and passes the server sanity check)
    assert col.sync() == 'success'
    assert col.find_note_ids(Front='from the other side') == [theirs.id]
    assert col.get_note(n1.id)['Back'] == 'edited remotely'
    with pytest.raises(KeyError): col.get_note(ncz.id)
    assert 'Oracle' in col.decks()

    # reverse: our deletion and tagged addition, verified by the oracle
    n2 = col.add(Front='round trip', tags=['back','forth'])
    col.remove_notes(n1.id)
    assert col.sync() == 'success'
    st = oc.sync_collection(auth, sync_media=False)
    oc.close()
    oc2 = AnkiCollection(str(tmp_path/'second'/'collection.anki2'))
    assert sorted(oc2.find_notes('')) == sorted([theirs.id, n2.id])
    assert oc2.find_notes('tag:forth') == [n2.id]
    ok = oc2.fix_integrity()[1]
    oc2.close()
    col.close()
    assert ok

# ---- fastanki-on-both-ends: conflict merge and full-sync bookkeeping ----

def _up(col, ep): return col.sync(user='tester', passw='s3kret', endpoint=ep, upload=True)

def test_merge_newer_wins(tmp_path):
    "Server changes must not clobber a newer local notetype/deck/deck_config; tags keep local flags"
    from fastanki.syncer import deck_to_s11, dconf_to_s11, nt_to_s11
    col = Collection.open(tmp_path/'m'/'collection.anki2')
    nid = col.q1('select id from notetypes where name=?', 'Basic')
    for t,i in [('decks',1),('deck_config',1),('notetypes',nid)]:
        col.con.execute(f'update {t} set mtime_secs=500 where id=?', (i,))

    # older incoming versions (mod=100) must be ignored, keeping the local mtime=500 copies
    d  = deck_to_s11(col.con, 1);  d['mod']=100;  d['name']='OLD DECK'
    dc = dconf_to_s11(col.con, 1); dc['mod']=100; dc['maxTaken']=1
    nt = nt_to_s11(col.con, nid);  nt['mod']=100; nt['css']='OLD CSS'
    col._apply_changes(dict(models=[nt], decks=[[d],[dc]]), 7)
    assert col.q1('select name from decks where id=1') == 'Default'
    assert col.q1('select mtime_secs from deck_config where id=1') == 500
    assert col.q1('select mtime_secs from notetypes where id=?', nid) == 500

    # a newer incoming deck (mod=900) is applied
    d2 = deck_to_s11(col.con, 1); d2['mod']=900; d2['name']='NEW DECK'
    col._apply_changes(dict(decks=[[d2],[]]), 8)
    assert col.q1('select name from decks where id=1') == 'NEW DECK'

    # a tag merge updates usn but preserves the local collapsed flag
    col.con.execute("insert into tags values ('vocab',5,1,NULL)")
    col._apply_changes(dict(tags=['vocab']), 12)
    assert col.q('select usn, collapsed from tags where tag=?', 'vocab') == [(12,1)]
    col.close()

def test_full_sync_usn(server, tmp_path):
    "full_download keeps the server usn; full_upload keeps every object usn <= col usn"
    ep = server
    a = Collection.open(tmp_path/'a'/'collection.anki2'); a.add(Front='one', Back='1')
    assert _up(a, ep) == 'full sync'

    b = Collection.open(tmp_path/'b'/'collection.anki2')
    assert b.sync(user='tester', passw='s3kret', endpoint=ep) == 'full sync'  # empty local -> download
    assert b.q1('select usn from col') != 0                                   # usn preserved, not zeroed

    b.add(Front='two', Back='2')
    assert b.sync() == 'success'                                              # delta assigns positive usns
    t = int(time.time()*1000) + 10000
    b.con.execute('update col set scm=?, mod=?', (t, t))      # simulate a schema change (bumps scm and mod)
    assert b.sync(upload=True) == 'full sync'                                 # forced full upload after deltas

    cu = b.q1('select usn from col')
    for t in ['notes','cards','revlog','notetypes','decks','deck_config','tags']:
        mx = b.q1(f'select coalesce(max(usn),0) from {t}')
        assert mx <= cu, (t, mx, cu)
    a.close(); b.close()

def test_sanity_failure(server, tmp_path):
    "A failed sanity check rolls the sync back, aborts the server, and bumps scm to force recovery"
    ep = server
    a = Collection.open(tmp_path/'a'/'collection.anki2'); a.add(Front='seed', Back='s')
    _up(a, ep)
    b = Collection.open(tmp_path/'b'/'collection.anki2')
    b.sync(user='tester', passw='s3kret', endpoint=ep)
    bn = b.add(Front='from B', Back='b'); b.sync()                            # server now has a change for a to pull

    time.sleep(0.01)  # col.mod is ms-resolution: let real time pass so a's next change post-dates B's sync
    an = a.add(Front='pending on A', Back='a')
    a._sanity_counts = lambda: [[0,0,0],1,1,1,1,1,1,1]                        # deliberately wrong counts
    scm0, mod0 = a.q1('select scm from col'), a.q1('select mod from col')
    with pytest.raises(SanityCheckFailed): a.sync()

    assert a.q1('select usn from notes where id=?', an.id) == -1             # local pending edit rolled back
    with pytest.raises(KeyError): a.get_note(bn.id)                          # server's change not half-applied
    assert a.q1('select mod from col') == mod0                              # sync not finalized
    assert a.q1('select scm from col') != scm0                             # scm bumped -> next sync is full

    del a._sanity_counts
    assert a.sync() == 'full sync'                                          # recovers by full download
    assert a.find_note_ids(Front='from B') == [bn.id]
    a.close(); b.close()

def test_dirty_monotonic(tmp_path):
    "col.mod strictly increases on every change, even when it already exceeds the wall clock"
    col = Collection.open(tmp_path/'d'/'collection.anki2')
    col.con.execute('update col set mod=?', (2**50,))   # mod far ahead of now_ms()
    before = col.q1('select mod from col')
    col._dirty()
    assert col.q1('select mod from col') > before
    col.close()

def test_concurrent_writers(tmp_path):
    "Concurrent writers on one collection file get distinct ids (BEGIN IMMEDIATE + busy_timeout serialize the ts_id read-then-insert)"
    p = tmp_path/'c'/'collection.anki2'
    Collection.open(p).close()                        # create the file
    def worker():
        c = Collection.open(p)
        for i in range(20): c.add(Front=f'{threading.get_ident()}-{i}', Back='x')
        c.close()
    ts = [threading.Thread(target=worker) for _ in range(4)]
    for t in ts: t.start()
    for t in ts: t.join()
    col = Collection.open(p)
    nids = [r[0] for r in col.q('select id from notes')]
    cids = [r[0] for r in col.q('select id from cards')]
    col.close()
    assert len(nids) == 80 and len(set(nids)) == 80   # every note landed, no id collision
    assert len(cids) == 80 and len(set(cids)) == 80

def test_grave_chunking(server, tmp_path):
    "Deleting more than CHUNK_SIZE notes syncs correctly via chunked graves"
    ep = server
    a = Collection.open(tmp_path/'a'/'collection.anki2')
    nids = [a.add(Front=f'q{i}', Back='x').id for i in range(300)]
    a.sync(user='tester', passw='s3kret', endpoint=ep, upload=True)
    b = Collection.open(tmp_path/'b'/'collection.anki2')
    b.sync(user='tester', passw='s3kret', endpoint=ep)
    assert b.q1('select count(*) from notes') == 300
    a.remove_notes(nids); a.sync()          # 300 note + 300 card graves -> 3 chunks of 250
    b.sync()
    assert b.q1('select count(*) from notes') == 0
    a.close(); b.close()

# ---- media sync ----

def _wait_media(oc):
    "The oracle's media sync runs in a backend thread; media_sync_status also rethrows its errors"
    while oc.media_sync_status().active: time.sleep(0.05)

def test_media_round_trip(server, tmp_path):
    ep = server
    col = Collection.open(tmp_path/'ours'/'collection.anki2')
    img = col.add_media(b'PNG our image', 'pic.png')
    assert img == 'pic.png'
    col.add(Front=f'What is this? <img src="{img}">', Back='our pic')
    col.sync(user='tester', passw='s3kret', endpoint=ep, upload=True)
    col.sync_media()
    col.sync_media()                                                  # caught up: a no-op

    # anki as second client: pull collection and media, verify bytes and reference integrity
    (tmp_path/'second').mkdir()
    oc = AnkiCollection(str(tmp_path/'second'/'collection.anki2'))
    auth = oc.sync_login('tester', 's3kret', endpoint=ep)
    st = oc.sync_collection(auth, sync_media=False)
    oc.close_for_full_sync()
    oc.full_upload_or_download(auth=auth, server_usn=st.server_media_usn, upload=False)
    oc.reopen(after_full_sync=True)
    oc.sync_media(auth); _wait_media(oc)
    med = Path(oc.media.dir())
    assert (med/'pic.png').read_bytes() == b'PNG our image'
    chk = oc.media.check()                                            # oracle: nothing missing, nothing unused
    assert not chk.missing and not chk.unused

    # oracle adds a file and deletes ours; we pull both (their file arrives, our deletion lands in media.trash)
    (tmp_path/'oracle.mp3').write_bytes(b'ORACLE AUDIO')
    oname = oc.media.add_file(str(tmp_path/'oracle.mp3'))
    oc.media.trash_files(['pic.png'])
    oc.sync_media(auth); _wait_media(oc)
    col.sync_media()
    with col.media() as m:
        assert (m.folder/oname).read_bytes() == b'ORACLE AUDIO'
        assert not (m.folder/'pic.png').exists()
        assert (m.folder.with_name('media.trash')/'pic.png').exists()
        assert m.pending(25) == [] and m.count() == 1

    # same name added on both sides with different bytes: the server's copy wins locally
    oc.media.write_data('clash.jpg', b'oracle version')
    oc.sync_media(auth); _wait_media(oc)
    col.add_media(b'our version', 'clash.jpg')
    col.sync_media()
    with col.media() as m:
        assert (m.folder/'clash.jpg').read_bytes() == b'oracle version'
        assert m.pending(25) == []

    # our deletion propagates to the oracle
    with col.media() as m: (m.folder/oname).unlink()
    col.sync_media()
    oc.sync_media(auth); _wait_media(oc)
    assert not (med/oname).exists()
    oc.close(); col.close()

def test_media_batching(server, tmp_path):
    "30 files exercise the 25-per-zip batch loops in both directions"
    ep = server
    a = Collection.open(tmp_path/'a'/'collection.anki2')
    for i in range(30): a.add_media(f'file {i}'.encode(), f'f{i:02}.txt')
    _up(a, ep)
    a.sync_media()
    b = Collection.open(tmp_path/'b'/'collection.anki2')
    b.sync(user='tester', passw='s3kret', endpoint=ep)
    b.sync_media()
    with b.media() as m:
        assert m.count() == 30 and m.meta()[1] == 30
        assert (m.folder/'f07.txt').read_bytes() == b'file 7'
        assert m.pending(25) == []
    a.close(); b.close()

def test_media_sanity_failure(server, tmp_path):
    "A failed count check clears the local media db; the next sync re-lists against the server"
    ep = server
    a = Collection.open(tmp_path/'a'/'collection.anki2')
    a.add_media(b'real', 'real.png')
    _up(a, ep)
    a.sync_media()
    # corrupt the db without touching the folder: a folder change would re-scan and clean the ghost up
    with a.media() as m:
        m.set_entry('ghost.png', '0'*40, 1, False)                    # inflates the local count
        m.set_entry('gone.txt', None, 0, True)                        # a pending deletion, so the sync acts and reaches the count check
    with pytest.raises(MediaSanityFailed): a.sync_media()
    with a.media() as m: assert m.count() == 0 and m.meta() == (0, 0) # forced resync
    a.sync_media()
    with a.media() as m:
        assert m.count() == 1 and m.pending(25) == []
        assert (m.folder/'real.png').read_bytes() == b'real'
    a.close()

def test_tool_schemas():
    "Every LLM tool produces a valid toolslm schema with described params"
    import fastanki
    from fastcore.funccall import get_schema
    tools = [fastanki.add_card, fastanki.add_fb_card, fastanki.add_cloze_card, fastanki.find_notes,
             fastanki.find_note_ids, fastanki.find_cards, fastanki.find_card_ids, fastanki.get_note,
             fastanki.del_note, fastanki.add_media, fastanki.update_fb_note, fastanki.sync]
    for f in tools:
        props = get_schema(f)['input_schema']['properties']   # raises if a param can't be schema'd
        assert props and all(v.get('description') for v in props.values()), f.__name__

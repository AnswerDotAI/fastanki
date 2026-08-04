# fastanki development notes

fastanki is a pure python implementation of Anki's collection file format and the AnkiWeb sync protocol. It does not use the `anki` package at runtime. Earlier versions did, and that caused constant trouble. The package is a thin wrapper over Anki's Rust library, which is written assuming the Qt desktop app is driving it, and errors surfaced as Rust panics and poisoned mutexes rather than Python exceptions. So this version reads and writes the sqlite file directly and speaks the sync protocol directly.

## Layout

This is an nbdev project. The notebooks in `nbs/` are the source of truth, and `nbdev-export` generates the modules in `fastanki/` from them. Don't edit the `.py` files. Each notebook mixes implementation, tests, and explanation, so the notebooks are also the detailed documentation for each layer.

- `00_schema.ipynb` (`schema.py`): the sqlite file format. Schema 18 DDL, the `unicase` collation, timestamps and id allocation, the default deck and deck config, the Basic and Cloze notetypes, and `create_collection`.
- `01_collection.ipynb` (`collection.py`): the `Collection` class. Notes, cards, decks, card generation, search, due counts, and the checksum, guid, and HTML stripping utilities Anki uses to fingerprint notes.
- `02_syncer.ipynb` (`syncer.py`): the AnkiWeb client. Login, the delta sync state machine, schema 11 conversions, full upload and download, and auth storage.
- `03_core.ipynb` (`core.py`): the functional API (`add_card`, `find_notes`, `sync`, etc). Each function opens the default collection, does its work, and closes. `anki_tools` exposes these as LLM tools.
- `04_media.ipynb` (`media.py`): media files and the media sync protocol. Filename normalization, the media db and folder scan, the zip wire format, and the media sync state machine.

`fastanki/_proto/` is not generated from a notebook. It vendors Anki's protobuf messages as serialized descriptors (`descriptors.binpb`), loaded at import into a private descriptor pool and exposed as module-shaped namespaces (`notetypes_pb2` etc), so the `anki` wheel's own registrations in the default pool never clash whatever version is installed. When an Anki update changes a proto we use, run `from fastanki._proto import refresh; refresh()` to re-dump the blob from the installed wheel. `tests/test_sync.py` is the end to end sync test, described below. `anki/` (gitignored) is a clone of the Anki source, kept for reference. When a protocol question comes up, the answer is in `anki/rslib/src/sync/`.

## Design

fastanki never opens a desktop Anki profile. It keeps its own collection, by default `~/.fastanki/collection.anki2` (set `FASTANKI_DIR` to change this), and other devices see changes through AnkiWeb sync like any other client. This matches where fastanki actually runs, which is servers and notebooks with no desktop Anki installed. It also limits what a bug can break to the local file, which a full download fixes.

Storage is schema 18 and sync is protocol version 11, the current versions of both. AnkiWeb still accepts the 2013-era protocol (sync versions 8 to 10), which needs no protobuf at all, but it is nearly unused and presumably on borrowed time. Using the current format also means a full download from AnkiWeb gives a file we can open as-is.

Protobuf appears only at rest. The wire protocol is zstd-compressed JSON, and notetypes, decks, and deck configs travel as the 2012 "schema 11" JSON dicts even at protocol 11, so `sync.py` converts between those dicts and our tables. Unknown keys are kept in an `other` field on both sides, which is how Anki itself round-trips fields it doesn't understand. That leaves five blob columns in the sqlite file (notetype, field, template, deck, and deck config settings) as the only protobuf, handled by the vendored pb2 modules and the standard protobuf runtime.

Search is keyword arguments compiled to SQL: `deck=`, `tag=`, `added_days=`, `is_due=`, field names as substring matches, and a raw `where=`/`args=` escape hatch. Anki's own search syntax is a 5,000 line parser in Rust, and we don't need it. Kwargs are simpler, and LLM tool calls get the search schema from the function signature.

The sync bookkeeping rules are: rows pending sync have `usn=-1`, and sending rewrites them to the server's usn. Deletions are recorded in `graves`. Every mutation bumps `col.mod`, which is how a sync knows there is work to do. All the mutating methods in `collection.py` follow these rules. The server compares object counts at the end of each sync (`sanityCheck2`), so a bookkeeping bug fails the sync instead of passing silently. On a sanity failure we bump `scm`, forcing the next sync to be a full one, which is Anki's own recovery path.

Media is supported: `add_media` copies a file into the collection's media folder (`collection.media`, with sync state in `collection.mdb`), and `sync()` runs a media sync after the collection sync. Media sync is a protocol of its own (endpoints under `msync/`, its own usn sequence, no full-sync path), implemented in `media.py` against `anki/rslib/src/sync/media/` as reference. The old rule "never create notes that reference media we can't upload" is discharged: the name `add_media` returns is always syncable.

A full upload replaces the server copy, and is the only operation here that can destroy remote data. So `sync()` never uploads unless called with `upload=True`, and even then it refuses to replace a non-empty server collection with an empty local one. Download has the mirror check. Before reading the file for upload we checkpoint the sqlite WAL, since otherwise the uploaded bytes are missing the most recent writes.

Storage goes through `apsw` rather than the stdlib `sqlite3`, for explicit, composable transactions. Each mutating method runs inside `Collection._tx()`, a context manager that issues `BEGIN IMMEDIATE` at the outermost level and nests via savepoints, so `ts_id`'s read-then-insert id allocation is atomic across connections and processes (the functional API in `core.py` opens a connection per call, so two `add_card`s can race otherwise). Connections are set up with `apsw.bestpractice` functions (WAL, a busy timeout, and double-quoted-strings off), so every SQL string literal uses single quotes.

## Testing

The `anki` package is a dev dependency and the tests use it as a reference implementation, in both directions. Files we create open cleanly in Anki, pass its `fix_integrity` check, and accept notes added through its API, and files Anki wrote are read and modified by us. Checksums, stripped text, and default object blobs are compared value by value against what Anki computes, and the schema 11 conversions round-trip dicts produced by Anki's API.

`tests/test_sync.py` covers sync end to end without touching the real AnkiWeb. The `anki` wheel includes AnkiWeb's protocol front end (media endpoints included), so `start_sync_server` in `syncer.py` launches `python -m anki.syncserver` on a free port; the pytest fixture and the notebooks' story cells both use it. Our client uploads, Anki logs in as a second client and verifies every note, tag, and deck, then edits and deletes and syncs the deltas back, and the same happens in reverse. Media gets the same treatment: bytes round-trip through Anki's media sync in both directions, deletions and same-name conflicts propagate, batching is exercised past the 25-file zip limit, and a count-check failure recovers. `pytest-timeout` bounds the whole run.

Run `pytest` for the sync test and `nbdev-test` for the notebooks. Cells that need a server process or AnkiWeb credentials are marked `eval: false` so CI and doc builds skip them, and no committed cell contains real credentials.

## Gotchas and Anki internals

Hard-won facts worth keeping. When a protocol question comes up the answer is in `anki/rslib/src/sync/`; these are the ones that cost time.

- Object ids (notes, cards, decks) are milliseconds-since-epoch and double as the creation time: `added_days` search is literally `id >= cutoff*1000`. They can't be plain sqlite rowids, because sync needs them unique across independent devices and they must never be reused after a delete. `ts_id` allocates them as `max(now_ms(), max_existing_id+1)`.
- `col.mod` is the collection's change-clock. The online sync decision is `remote.mod == local.mod -> noChanges` (`meta.rs`), checked *before* the schema check. Because fastanki mutates far faster than a human driving the GUI, two operations (or a change right after a sync's finish) can share a millisecond and a real change then looks like "no change". `_dirty` uses `max(now_ms(), mod+1)` to keep `mod` strictly increasing; Anki avoids the collision only by being slow.
- A real schema change bumps both `scm` and `mod`. Since meta checks `mod` equality before `scm`, bumping `scm` alone never triggers a full sync (a test learned this the hard way).
- Unchunked-changes merge is mtime-based: the server gathers its notetype/deck/deck_config changes *before* merging your upload, so it can hand back its own copy. Apply an incoming one only if `existing.mtime_secs <= incoming.mtime` (`changes.rs`), or you clobber a newer local copy. Notes and cards get the same newer-wins guard in the chunk path. We have no in-place edit API for notetypes/decks/deck_config, so today the merge guard is latent (nothing local is ever newer), but it defends the contract.
- `before_upload` resets usns asymmetrically (`collection/mod.rs`): notes/cards/revlog clear only pending rows (`usn=-1 -> 0`), but decks/notetypes/deck_config/tags reset every row (`usn!=0 -> 0`), and `col.usn` increments. Client-side `full_download` only runs `update col set ls=mod`, keeping the file's usn; the server side is what increments it.
- A failed `sanityCheck2` is a rollback, not a checkpoint: roll back the whole sync, abort the server session, and bump `scm` to force a full sync next time (`normal.rs`). Counts tuple order is `[[0,0,0], cards, notes, revlog, graves, notetypes, decks, deck_config]`; the server zeroes graves and due-counts before comparing (`sanity.rs`), and the reply status is `'ok'`/`'bad'`.
- `config.curModel` is a per-collection notetype id (a timestamp), so exclude it when comparing the `config` table against the oracle.
- The AnkiWeb sync client lives in `syncer.py` (module `fastanki.syncer`), named so it doesn't collide with core's top-level `sync` function; `from fastanki import *` exposes both, and `SyncServer`/`sync_collection`/etc. come from `fastanki.syncer`.
- `apsw` (not stdlib `sqlite3`): connections have no `.commit()`/`.rollback()` (autocommit unless inside an explicit transaction), `execute` runs multiple statements so there is no `executescript`, and double-quoted strings are disabled, so SQL string literals must use single quotes. Mutations go through `Collection._tx()`; sync uses explicit `BEGIN IMMEDIATE`/`COMMIT`/`ROLLBACK`. The busy timeout is set before the WAL pragma, else concurrent opens hit `BusyError` on the journal-mode switch.
- Media sync wire quirks (`sync/media/protocol.rs`): JSON replies are wrapped in a legacy `{"data": ..., "err": ""}` envelope, and `serde_tuple` structs travel as JSON *arrays*: a change row is `[fname, usn, sha1]`, an upload reply `[processed, current_usn]`. The upload zip's `_meta` is a list of `[name, zipname|null]` pairs (null = deletion), but a download zip's is a `{zipname: name}` dict.
- Media db mtimes mix units: the folder mtime cache (`dirMod`) is milliseconds, per-file mtimes are seconds. Deletions are detected only by the folder scan, and the scan is skipped entirely when the folder mtime is unchanged - so tests that fake db state must not touch the folder, or the scan will "repair" the fake.
- After a media upload, adopt the server's usn only if `lastUsn + files_sent == current_usn`; anything else means another client uploaded concurrently and the next fetch must see their rows (`syncer.rs`).
- Anki's add-media-uniquely lowercases: a fresh uppercase filename is stored lowercased, but the same-name-same-content check runs against the original case first, so on a case-insensitive filesystem re-adding `Foo.jpg` returns `Foo.jpg` while Linux returns `foo.jpg`. Don't pin the mixed-case result in a test.
- A failed `mediaSanity` count check (deleted entries excluded) clears the whole media db so the next sync re-lists against the server; media has no full-sync path, so this is its only recovery mechanism.

## Not implemented

Filtered decks aren't supported. The schema 11 conversions assert if they meet one, so syncing such a collection fails rather than corrupting it.

There is no scheduler. We count due cards but can't answer them. If reviewing is ever wanted, FSRS is available as a pure python package, so the Rust scheduler wouldn't need porting.

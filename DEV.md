# fastanki development notes

fastanki is a pure python implementation of Anki's collection file format and the AnkiWeb sync protocol. It does not use the `anki` package at runtime. Earlier versions did, and that caused constant trouble. The package is a thin wrapper over Anki's Rust library, which is written assuming the Qt desktop app is driving it, and errors surfaced as Rust panics and poisoned mutexes rather than Python exceptions. So this version reads and writes the sqlite file directly and speaks the sync protocol directly.

## Layout

This is an nbdev project. The notebooks in `nbs/` are the source of truth, and `nbdev-export` generates the modules in `fastanki/` from them. Don't edit the `.py` files. Each notebook mixes implementation, tests, and explanation, so the notebooks are also the detailed documentation for each layer.

- `00_schema.ipynb` (`schema.py`): the sqlite file format. Schema 18 DDL, the `unicase` collation, timestamps and id allocation, the default deck and deck config, the Basic and Cloze notetypes, and `create_collection`.
- `01_collection.ipynb` (`collection.py`): the `Collection` class. Notes, cards, decks, card generation, search, due counts, and the checksum, guid, and HTML stripping utilities Anki uses to fingerprint notes.
- `02_syncer.ipynb` (`syncer.py`): the AnkiWeb client. Login, the delta sync state machine, schema 11 conversions, full upload and download, and auth storage.
- `03_fsrs.ipynb` (`fsrs.py`): the FSRS-6 memory model, a pure port of the scheduling half of the `fsrs-rs` crate Anki embeds: parameter upgrading/clipping (17/19/21-length sets), the forgetting curve, memory-state updates, and the SM-2 approximation for truncated histories. No card or collection knowledge.
- `04_scheduler.ipynb` (`scheduler.py`): reviewing. The v3 scheduler state machine (new/learning/review/relearning, SM-2 and FSRS), interval fuzz, `answer_card` with its revlog/counter/leech bookkeeping, `answer_buttons`, and a simplified `next_card` queue with daily limits and sibling burying.
- `05_core.ipynb` (`core.py`): the functional API (`add_card`, `find_notes`, `sync`, etc). Each function opens the default collection, does its work, and closes. `anki_tools` exposes these as LLM tools.

`fastanki/_proto/` is not generated from a notebook. It contains protobuf modules copied from the `anki` wheel with imports rewritten, and can be refreshed the same way from a newer wheel if needed. `tests/test_sync.py` is the end to end sync test, described below. `anki/` (gitignored) is a clone of the Anki source, kept for reference. When a protocol question comes up, the answer is in `anki/rslib/src/sync/`; for scheduling, `anki/rslib/src/scheduler/` and the `fsrs-rs/` clone (also gitignored).

## Design

fastanki never opens a desktop Anki profile. It keeps its own collection, by default `~/.fastanki/collection.anki2` (set `FASTANKI_DIR` to change this), and other devices see changes through AnkiWeb sync like any other client. This matches where fastanki actually runs, which is servers and notebooks with no desktop Anki installed. It also limits what a bug can break to the local file, which a full download fixes.

Storage is schema 18 and sync is protocol version 11, the current versions of both. AnkiWeb still accepts the 2013-era protocol (sync versions 8 to 10), which needs no protobuf at all, but it is nearly unused and presumably on borrowed time. Using the current format also means a full download from AnkiWeb gives a file we can open as-is.

Protobuf appears only at rest. The wire protocol is zstd-compressed JSON, and notetypes, decks, and deck configs travel as the 2012 "schema 11" JSON dicts even at protocol 11, so `sync.py` converts between those dicts and our tables. Unknown keys are kept in an `other` field on both sides, which is how Anki itself round-trips fields it doesn't understand. That leaves five blob columns in the sqlite file (notetype, field, template, deck, and deck config settings) as the only protobuf, handled by the vendored pb2 modules and the standard protobuf runtime.

Search is keyword arguments compiled to SQL: `deck=`, `tag=`, `added_days=`, `is_due=`, field names as substring matches, and a raw `where=`/`args=` escape hatch. Anki's own search syntax is a 5,000 line parser in Rust, and we don't need it. Kwargs are simpler, and LLM tool calls get the search schema from the function signature.

The sync bookkeeping rules are: rows pending sync have `usn=-1`, and sending rewrites them to the server's usn. Deletions are recorded in `graves`. Every mutation bumps `col.mod`, which is how a sync knows there is work to do. All the mutating methods in `collection.py` follow these rules. The server compares object counts at the end of each sync (`sanityCheck2`), so a bookkeeping bug fails the sync instead of passing silently. On a sanity failure we bump `scm`, forcing the next sync to be a full one, which is Anki's own recovery path.

A full upload replaces the server copy, and is the only operation here that can destroy remote data. So `sync()` never uploads unless called with `upload=True`, and even then it refuses to replace a non-empty server collection with an empty local one. Download has the mirror check. Before reading the file for upload we checkpoint the sqlite WAL, since otherwise the uploaded bytes are missing the most recent writes.

Storage goes through `apsw` rather than the stdlib `sqlite3`, for explicit, composable transactions. Each mutating method runs inside `Collection._tx()`, a context manager that issues `BEGIN IMMEDIATE` at the outermost level and nests via savepoints, so `ts_id`'s read-then-insert id allocation is atomic across connections and processes (the functional API in `core.py` opens a connection per call, so two `add_card`s can race otherwise). Connections are set up with `apsw.bestpractice` functions (WAL, a busy timeout, and double-quoted-strings off), so every SQL string literal uses single quotes.

## Testing

The `anki` package is a dev dependency and the tests use it as a reference implementation, in both directions. Files we create open cleanly in Anki, pass its `fix_integrity` check, and accept notes added through its API, and files Anki wrote are read and modified by us. Checksums, stripped text, and default object blobs are compared value by value against what Anki computes, and the schema 11 conversions round-trip dicts produced by Anki's API.

`tests/test_sync.py` covers sync end to end without touching the real AnkiWeb. The `anki` wheel includes AnkiWeb's protocol front end, so a fixture starts `python -m anki.syncserver` in a subprocess on a random port. Our client uploads, Anki logs in as a second client and verifies every note, tag, and deck, then edits and deletes and syncs the deltas back, and the same happens in reverse. `pytest-timeout` bounds the whole run.

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
- Scheduling gotchas, learned porting `rslib/src/scheduler/` for `04_scheduler.ipynb`: `ANKI_TEST_MODE=1` (set before the `anki` package first computes states) disables the oracle's interval fuzz, which is what makes exact scheduling comparisons possible. Fuzz is seeded per `(card_id + reps)`, but Anki seeds Rust's ChaCha12 and we seed Python's Mersenne twister, so the two pick different (equally valid) points inside identical fuzz bounds; everything else is deterministic. Anki computes in f32: keep the protobuf floats raw (1.3 is really 1.2999999523) and round half-away-from-zero (`_round`), or intervals drift by a day at rounding boundaries.
- fsrs-rs version matters: Anki 26.05 pins fsrs 6.6.1, whose same-day (short-term) stability floors the multiplier at 1 for Good/Easy only; 6.6.2+ floors Hard too. We match 6.6.1 -- the twin-collection oracle test caught this, and it's the arbiter if the pin moves.
- The `cards.data` JSON carries `pos` (original new-queue position), `lrt` (last review time), and under FSRS `s`/`d`/`dr`/`decay`, rounded to 4/3/2/3 decimal places respectively. Anki clears `s`/`d`/`dr` when answering with FSRS off but leaves `decay` alone.

## Not implemented

Media sync is a separate protocol and is skipped entirely. That is safe, because collection sync moves note rows and media sync moves files, and the two don't interfere. The one rule is to never create notes that reference media files we can't upload, so the API has no way to attach media.

Filtered decks aren't supported. The schema 11 conversions assert if they meet one, so syncing such a collection fails rather than corrupting it.

The scheduler covers normal decks only: answering a card in a filtered deck raises. The `next_card` queue is a simplified port of Anki's v3 builder -- daily limits come from the named deck's preset rather than a per-subdeck limit tree, gathering is by due order, reviews precede new cards, and there is no display-order matrix. Those simplifications affect session ordering, never scheduling state, so they can be extended without compatibility concerns. The FSRS optimizer is deliberately absent: parameters arrive through deck-config sync, and users can optimize from Anki desktop (scheduling with synced-or-default parameters is exactly what AnkiWeb's own study feature does).

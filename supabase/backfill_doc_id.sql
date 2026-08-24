-- =============================================================================
-- ARIS — backfill documents.doc_id and documents.section_tag
-- =============================================================================
--
-- WHY THIS EXISTS
--   pipeline/chunker.py never copied `doc_id` / `section_tag` out of the metadata
--   dict, so pipeline/vector_store.py:79-81 wrote '' into every `documents` row.
--   Every doc_id-filtered query therefore matched nothing. The code path is now
--   fixed, but rows ingested before that fix still hold ''. This script repairs
--   them.
--
-- WHY IT JOINS INSTEAD OF RECOMPUTING md5(b2_key)
--   ingestor.py:149 derives doc_id as md5(b2_key), so recomputing it in SQL looks
--   equivalent. It is not, and the difference matters:
--
--     * doc_metadata.doc_id (written from the SAME dict, vector_store.py:109) is
--       the value the frontend routes with and the API filters on. It is
--       authoritative.
--     * Recomputing derives a SECOND value and assumes it still agrees. If it
--       doesn't -- an older ingest hashing different input, a b2_key mutated after
--       ingest, or an encoding mismatch between Python's .encode('utf-8') and
--       Postgres md5() -- the chunks get a doc_id that nothing queries.
--     * That failure is SILENT. Chat returns "I could not find relevant
--       information", which is indistinguishable from the bug being fixed here.
--
--   Copying the authoritative value cannot drift from it. So: join on b2_key,
--   and use md5() only as a consistency CHECK (STEP 2).
--
-- HOW TO RUN
--   Run STEP 0 through STEP 2 first and read the output. They are read-only.
--   Only run STEP 3 if the gates below pass. STEP 3 is a transaction you must
--   COMMIT yourself.
--
-- =============================================================================


-- -----------------------------------------------------------------------------
-- STEP 0 (read-only) — GATE: is b2_key unique in doc_metadata?
-- -----------------------------------------------------------------------------
-- UPDATE ... FROM picks an ARBITRARY row when several match, so duplicate
-- b2_key values with differing doc_id would make STEP 3 non-deterministic.
-- ingestor.py:192 checks-then-inserts, which is racy and not a constraint.
--
-- EXPECTED: 0 rows.
-- IF ROWS COME BACK: stop. Resolve the duplicates first (decide which doc_id is
-- canonical, delete the rest), then re-run this gate.

SELECT
    b2_key,
    count(*)                        AS metadata_rows,
    count(DISTINCT doc_id)          AS distinct_doc_ids,
    array_agg(DISTINCT doc_id)      AS doc_ids
FROM doc_metadata
GROUP BY b2_key
HAVING count(*) > 1
ORDER BY count(*) DESC;


-- -----------------------------------------------------------------------------
-- STEP 1 (read-only) — scope of the repair
-- -----------------------------------------------------------------------------
-- Confirms there is something to fix and that doc_metadata is populated enough
-- to fix it with.

SELECT
    (SELECT count(*) FROM documents)                                  AS total_chunks,
    (SELECT count(*) FROM documents WHERE doc_id IS NULL OR doc_id = '')
                                                                      AS chunks_missing_doc_id,
    (SELECT count(*) FROM documents WHERE section_tag IS NULL OR section_tag = '')
                                                                      AS chunks_missing_section_tag,
    (SELECT count(*) FROM doc_metadata)                               AS metadata_rows,
    (SELECT count(*) FROM doc_metadata WHERE doc_id IS NULL OR doc_id = '')
                                                                      AS metadata_rows_missing_doc_id;


-- -----------------------------------------------------------------------------
-- STEP 2 (read-only) — GATE: does md5(b2_key) still agree with the stored doc_id?
-- -----------------------------------------------------------------------------
-- This is the assumption check. Postgres md5(text) on a UTF-8 database produces
-- the same digest as Python hashlib.md5(s.encode('utf-8')).hexdigest(), so every
-- row SHOULD agree.
--
-- Checking all rows costs the same as checking one and is strictly stronger than
-- spot-checking a single known document.
--
-- EXPECTED: disagreeing = 0.
--
-- IF disagreeing > 0: do NOT let that stop STEP 3 -- it is precisely the evidence
-- that recomputing md5() would have written wrong doc_ids. The join in STEP 3
-- ignores md5() entirely and remains correct. What a mismatch DOES tell you is
-- that some b2_key values changed after ingest, so inspect the samples below and
-- confirm those B2 objects still exist before trusting their chunks.

SELECT
    count(*)                                                    AS metadata_rows_checked,
    count(*) FILTER (WHERE doc_id = md5(b2_key))                AS agreeing,
    count(*) FILTER (WHERE doc_id <> md5(b2_key))               AS disagreeing
FROM doc_metadata
WHERE b2_key IS NOT NULL
  AND b2_key <> ''
  AND doc_id IS NOT NULL
  AND doc_id <> '';

-- Sample any mismatches for inspection.
SELECT
    b2_key,
    doc_id          AS stored_doc_id,
    md5(b2_key)     AS recomputed_doc_id,
    doc_name
FROM doc_metadata
WHERE b2_key IS NOT NULL
  AND b2_key <> ''
  AND doc_id IS NOT NULL
  AND doc_id <> ''
  AND doc_id <> md5(b2_key)
LIMIT 20;


-- -----------------------------------------------------------------------------
-- STEP 2b (read-only) — coverage: chunks the join CANNOT reach
-- -----------------------------------------------------------------------------
-- ingestor.py only writes doc_metadata when a row is absent (:192, :231) and
-- save_doc_metadata swallows its own failures (vector_store.py:119-121), so
-- `documents` rows can exist with no doc_metadata partner. Those cannot be
-- backfilled by join.
--
-- These are NOT repaired by STEP 3. Re-ingesting the listed b2_keys is the
-- correct fix -- that regenerates both tables from the live B2 object rather than
-- inventing a doc_id for a document whose metadata was never recorded.

SELECT
    d.b2_key,
    d.source,
    d.doc_name,
    count(*) AS orphan_chunks
FROM documents d
LEFT JOIN doc_metadata m ON m.b2_key = d.b2_key
WHERE m.b2_key IS NULL
GROUP BY d.b2_key, d.source, d.doc_name
ORDER BY count(*) DESC;


-- =============================================================================
-- STEP 3 — THE REPAIR (writes data)
-- =============================================================================
-- Gates before running:
--   [ ] STEP 0 returned 0 rows (b2_key is unique in doc_metadata)
--   [ ] STEP 1 shows chunks_missing_doc_id > 0 (there is work to do)
--   [ ] STEP 2b output reviewed and accepted (those chunks stay unrepaired)
--
-- Run as one block. Inspect the verification output, THEN commit.

BEGIN;

-- 3a — copy the authoritative doc_id from doc_metadata, matched on b2_key.
UPDATE documents d
SET    doc_id = m.doc_id
FROM   doc_metadata m
WHERE  d.b2_key = m.b2_key
  AND  (d.doc_id IS NULL OR d.doc_id = '')
  AND  m.doc_id IS NOT NULL
  AND  m.doc_id <> '';

-- 3b — fill section_tag (the category slug) from the same join.
--
-- Note the column asymmetry: doc_metadata has only `section`, and
-- save_doc_metadata (vector_store.py:112) stores the category slug there. In
-- `documents`, `section` holds the in-document heading detected by
-- chunker.py:97 and `section_tag` holds the slug. So doc_metadata.section is
-- the correct source for documents.section_tag -- NOT for documents.section,
-- which must not be touched or it would overwrite real headings.
UPDATE documents d
SET    section_tag = m.section
FROM   doc_metadata m
WHERE  d.b2_key = m.b2_key
  AND  (d.section_tag IS NULL OR d.section_tag = '')
  AND  m.section IS NOT NULL
  AND  m.section <> '';

-- 3c — VERIFY before committing.
--
-- Expect: still_missing_doc_id equals the orphan chunk count from STEP 2b, and
-- mismatched_against_metadata = 0. If mismatched > 0, ROLLBACK.
SELECT
    count(*) FILTER (WHERE d.doc_id IS NULL OR d.doc_id = '')     AS still_missing_doc_id,
    count(*) FILTER (WHERE d.doc_id IS NOT NULL AND d.doc_id <> '') AS now_populated,
    count(*) FILTER (
        WHERE m.doc_id IS NOT NULL
          AND m.doc_id <> ''
          AND d.doc_id <> m.doc_id
    )                                                             AS mismatched_against_metadata
FROM documents d
LEFT JOIN doc_metadata m ON m.b2_key = d.b2_key;

-- Sanity check: every distinct doc_id in `documents` should now be routable,
-- i.e. present in doc_metadata. Expect 0 rows.
SELECT DISTINCT d.doc_id
FROM documents d
LEFT JOIN doc_metadata m ON m.doc_id = d.doc_id
WHERE d.doc_id IS NOT NULL
  AND d.doc_id <> ''
  AND m.doc_id IS NULL;

-- Reviewed and correct?
COMMIT;
-- Something looks wrong?
-- ROLLBACK;


-- =============================================================================
-- AFTER COMMITTING — end-to-end check against the running app
-- =============================================================================
-- Pick any document the UI links to and confirm its chunks are now reachable:
--
--   SELECT doc_id, b2_key, doc_name FROM doc_metadata LIMIT 1;
--
-- Then, with that doc_id, confirm the chunk count is non-zero:
--
--   SELECT count(*) FROM documents WHERE doc_id = '<paste doc_id>';
--
-- Finally open that document in the UI and ask its chat panel a question. Before
-- this backfill it answered "I could not find relevant information"; it should
-- now cite that document. Global chat (no doc_id filter) worked already and
-- should be unchanged.
-- =============================================================================

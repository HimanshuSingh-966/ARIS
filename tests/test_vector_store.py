"""
tests/test_vector_store.py

Covers pipeline/vector_store.save_chunks() and its rollback path.

The bug this suite exists for: save_chunks writes in batches of 50, each one a
separate autocommitted request, and it used to catch the failure and *return the
partial count*. doc_already_ingested() asks only whether **any** chunk exists for a
b2_key, so a document that died after batch 3 of 9 left 150 rows behind, was skipped
as "already ingested" on every subsequent run, and stayed two-thirds empty for the
life of the database. Worse, the non-zero return made ingestor.process_document
report status "done", count it under `Docs ingested`, and write its doc_metadata row
— so the document appeared fully browsable in the UI. Nothing logged an error.

A Ctrl-C during a multi-hour ingest is the likeliest way to trigger it, and
KeyboardInterrupt is a *sibling* of Exception rather than a subclass, so the original
`except Exception` did not even see the most probable case.

No network and no Supabase: a fake client is injected into the module's cached
`_client` global.
"""

import logging

import pytest

from pipeline import vector_store


# ── Fake Supabase client ──────────────────────────────────────────────────────

class _Result:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    """
    Supports exactly the two call chains save_chunks uses:
        .insert(rows).execute()
        .delete().eq(col, val).execute()
    """

    def __init__(self, db, fail_on_batch=None, fail_delete=False, exc=RuntimeError):
        self.db            = db
        self.fail_on_batch = fail_on_batch
        self.fail_delete   = fail_delete
        self.exc           = exc
        self.batches       = 0
        self.deletes       = 0
        self._op           = None
        self._filters      = {}

    def insert(self, rows):
        self._op = ("insert", rows)
        return self

    def delete(self):
        self._op      = ("delete", None)
        self._filters = {}
        return self

    def eq(self, column, value):
        self._filters[column] = value
        return self

    def execute(self):
        kind, payload = self._op
        if kind == "insert":
            self.batches += 1
            if self.batches == self.fail_on_batch:
                raise self.exc("simulated failure")
            self.db.extend(payload)
            return _Result(list(payload))

        self.deletes += 1
        if self.fail_delete:
            raise RuntimeError("simulated delete failure")
        keep, removed = [], []
        for row in self.db:
            if all(row.get(c) == v for c, v in self._filters.items()):
                removed.append(row)
            else:
                keep.append(row)
        self.db[:] = keep
        return _Result(removed)


class _FakeClient:
    def __init__(self, table):
        self._table = table

    def table(self, name):
        assert name == "documents", f"unexpected table {name!r}"
        return self._table


@pytest.fixture
def fake(monkeypatch):
    """Install a fake client and hand the test its row store and table."""
    def _install(fail_on_batch=None, fail_delete=False, exc=RuntimeError, db=None):
        rows  = [] if db is None else db
        table = _FakeTable(rows, fail_on_batch, fail_delete, exc)
        monkeypatch.setattr(vector_store, "_client", _FakeClient(table))
        return table
    return _install


def make_chunks(n, b2_key="cdsco/test-doc.pdf", embed=True):
    chunks = []
    for i in range(n):
        chunk = {
            "source":      "cdsco",
            "country":     "India",
            "doc_name":    "test-doc",
            "section":     "",
            "section_tag": "clinical-trials",
            "doc_id":      "d41d8cd98f00b204e9800998ecf8427e",
            "content":     f"chunk {i} body text",
            "b2_key":      b2_key,
            "source_url":  "",
            "char_start":  i * 1000,
            "char_end":    i * 1000 + 1200,
        }
        if embed:
            chunk["embedding"] = [0.0] * 384
        chunks.append(chunk)
    return chunks


# ── Happy path ────────────────────────────────────────────────────────────────

def test_no_chunks_is_a_no_op(fake):
    table = fake()
    assert vector_store.save_chunks([]) == 0
    assert table.batches == 0


def test_all_batches_saved_returns_the_full_count(fake):
    table = fake()
    assert vector_store.save_chunks(make_chunks(120)) == 120
    assert table.batches == 3          # 50 + 50 + 20
    assert len(table.db) == 120
    assert table.deletes == 0


def test_chunks_without_an_embedding_are_skipped(fake):
    table = fake()
    chunks = make_chunks(2) + make_chunks(1, embed=False)
    assert vector_store.save_chunks(chunks) == 2
    assert len(table.db) == 2


def test_all_chunks_unembedded_writes_nothing(fake):
    table = fake()
    assert vector_store.save_chunks(make_chunks(3, embed=False)) == 0
    assert table.batches == 0


# ── The rollback ──────────────────────────────────────────────────────────────

def test_partial_failure_rolls_back_and_raises(fake, caplog):
    """The core fix: no partial rows survive, and no count is returned."""
    table = fake(fail_on_batch=3)
    with caplog.at_level(logging.WARNING, logger="pipeline.vector_store"):
        with pytest.raises(RuntimeError):
            vector_store.save_chunks(make_chunks(200))   # 4 batches, dies on the 3rd
    assert table.batches == 3
    assert table.db == [], "partial rows must not survive — they poison the skip check"
    assert "Rolled back 100 partial chunks" in caplog.text


def test_keyboard_interrupt_also_rolls_back(fake):
    """
    KeyboardInterrupt is a sibling of Exception, not a subclass, so the original
    `except Exception` missed the most likely interruption of a long ingest. It must
    still clean up, and must still propagate so the run actually stops.
    """
    table = fake(fail_on_batch=2, exc=KeyboardInterrupt)
    with pytest.raises(KeyboardInterrupt):
        vector_store.save_chunks(make_chunks(120))
    assert table.db == []
    assert table.deletes == 1


def test_first_batch_failure_needs_no_rollback(fake, caplog):
    table = fake(fail_on_batch=1)
    with caplog.at_level(logging.WARNING, logger="pipeline.vector_store"):
        with pytest.raises(RuntimeError):
            vector_store.save_chunks(make_chunks(120))
    assert table.db == []
    assert table.deletes == 0, "nothing landed, so nothing should be deleted"
    assert "Rolled back" not in caplog.text


def test_rollback_only_touches_this_document(fake):
    """The delete is filtered on b2_key; another document's rows must survive."""
    other = make_chunks(2, b2_key="ema/other-doc.pdf")
    table = fake(fail_on_batch=2, db=list(other))
    with pytest.raises(RuntimeError):
        vector_store.save_chunks(make_chunks(120))
    assert [r["b2_key"] for r in table.db] == ["ema/other-doc.pdf"] * 2


def test_failed_rollback_logs_the_recovery_sql(fake, caplog):
    """
    If the delete fails too, the orphaned rows remain and the document is
    unreachable forever. That is the one case a human has to fix, so the log has to
    name it and give the statement.
    """
    table = fake(fail_on_batch=2, fail_delete=True)
    with caplog.at_level(logging.ERROR, logger="pipeline.vector_store"):
        with pytest.raises(RuntimeError):
            vector_store.save_chunks(make_chunks(120))
    assert len(table.db) == 50, "the failed delete leaves the partial rows in place"
    assert "ROLLBACK FAILED" in caplog.text
    assert "delete from documents where b2_key = 'cdsco/test-doc.pdf';" in caplog.text


def test_missing_b2_key_reports_that_no_safe_filter_exists(fake, caplog):
    """
    Chunks fall back to b2_key='' when metadata omits it. `.eq("b2_key", "")` would
    match those rows across every document, so the rollback must refuse rather than
    delete by an empty filter.
    """
    table  = fake(fail_on_batch=2)
    chunks = make_chunks(120, b2_key="")
    with caplog.at_level(logging.ERROR, logger="pipeline.vector_store"):
        with pytest.raises(RuntimeError):
            vector_store.save_chunks(chunks)
    assert table.deletes == 0
    assert len(table.db) == 50
    assert "no single b2_key" in caplog.text


# ── delete_chunks_for_doc ─────────────────────────────────────────────────────

def test_delete_chunks_for_doc_removes_matching_rows(fake):
    table = fake(db=make_chunks(3) + make_chunks(2, b2_key="ema/other.pdf"))
    assert vector_store.delete_chunks_for_doc("cdsco/test-doc.pdf") == 3
    assert len(table.db) == 2


def test_delete_chunks_for_doc_refuses_an_empty_key(fake, caplog):
    table = fake(db=make_chunks(3))
    with caplog.at_level(logging.ERROR, logger="pipeline.vector_store"):
        assert vector_store.delete_chunks_for_doc("") == -1
    assert table.deletes == 0
    assert len(table.db) == 3, "an empty filter must not delete anything"


def test_delete_chunks_for_doc_returns_minus_one_on_failure(fake):
    """-1, not 0: 'nothing to delete' and 'the delete failed' must be tellable
    apart, because only the second leaves the document permanently skipped."""
    fake(fail_delete=True, db=make_chunks(3))
    assert vector_store.delete_chunks_for_doc("cdsco/test-doc.pdf") == -1

"""
tests/test_api_utils.py

Covers api/utils.py. The contract worth defending is narrow but absolute: whatever
comes out of safe_content_disposition() must be Latin-1 encodable (or the ASGI
server raises while encoding the response, 500ing an otherwise valid document) and
must not let a database-supplied filename inject or truncate headers.
"""

import pytest

from api.utils import pdf_filename, safe_content_disposition


# ── pdf_filename ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("given, expected", [
    ("notice", "notice.pdf"),
    ("notice.pdf", "notice.pdf"),          # must not double the extension
    ("notice.PDF", "notice.PDF"),          # case-insensitive check, case preserved
    ("  spaced  ", "spaced.pdf"),
    ("", "document.pdf"),
    (None, "document.pdf"),
])
def test_pdf_filename(given, expected):
    assert pdf_filename(given) == expected


def test_pdf_filename_custom_fallback():
    assert pdf_filename("", fallback="form") == "form.pdf"


# ── safe_content_disposition ──────────────────────────────────────────────────

def test_plain_name_is_left_alone():
    assert safe_content_disposition("notice.pdf") == 'inline; filename="notice.pdf"'


def test_attachment_disposition():
    assert safe_content_disposition("f.pdf", "attachment").startswith("attachment; ")


def test_invalid_disposition_rejected():
    with pytest.raises(ValueError):
        safe_content_disposition("f.pdf", "inline; drop-table")


def test_crlf_cannot_inject_a_header():
    """
    The property that matters is that the value stays a single header line. The
    stripped remainder ("X-Evil: 1") stays inside the quoted filename, which is
    harmless — a quoted-string may contain ':' and spaces.
    """
    value = safe_content_disposition("a\r\nX-Evil: 1.pdf")
    assert "\r" not in value and "\n" not in value
    assert value.count('"') == 2
    assert value == 'inline; filename="aX-Evil: 1.pdf"'


def test_double_quote_cannot_truncate_the_filename_parameter():
    value = safe_content_disposition('a"b.pdf')
    # Exactly two quotes: the ones delimiting the parameter.
    assert value.count('"') == 2


def test_quote_is_not_smuggled_back_through_the_extended_form():
    """
    The regression this exists for: filename* used to be percent-encoded from the
    *raw* input, so a stripped `"` came back intact for any client that decodes it.
    """
    value = safe_content_disposition('a"b.pdf')
    assert "%22" not in value


def test_path_traversal_is_not_smuggled_back_either():
    value = safe_content_disposition("../../etc/passwd.pdf")
    assert "/" not in value
    assert "%2F" not in value.upper()
    assert ".." not in value


def test_all_non_ascii_stem_does_not_promote_the_extension():
    """An all-CJK name used to fold to filename="pdf" — the extension became the name."""
    value = safe_content_disposition("测试文档.pdf")
    assert 'filename="document.pdf"' in value
    # The real name still reaches capable clients.
    assert "filename*=UTF-8''" in value


def test_accents_fold_to_base_letters_rather_than_vanishing():
    value = safe_content_disposition("Zulassungsprüfung.pdf")
    assert 'filename="Zulassungsprufung.pdf"' in value


def test_no_extended_form_when_it_adds_nothing():
    assert "filename*" not in safe_content_disposition("plain.pdf")


def test_empty_and_fully_stripped_names_fall_back():
    """`fallback` is a stem, so no extension is invented when none survived."""
    assert safe_content_disposition("") == 'inline; filename="document"'
    assert safe_content_disposition("...") == 'inline; filename="document"'


def test_a_name_of_only_unsafe_characters_keeps_its_extension():
    """
    Regression: stripping '"""' from '""".pdf' leaves '.pdf', and lstrip('.') used
    to fold that into the stem position — yielding filename="pdf", the extension
    masquerading as the filename.
    """
    assert safe_content_disposition('""".pdf') == 'inline; filename="document.pdf"'
    assert safe_content_disposition("///doc.pdf") == 'inline; filename="doc.pdf"'


def test_fallback_stem_does_not_trigger_a_redundant_extended_form():
    assert "filename*" not in safe_content_disposition('""".pdf')


def test_pdf_filename_composes_with_the_sanitiser():
    """How the routes actually call it: pdf_filename supplies the extension, the
    sanitiser makes the result header-safe."""
    assert safe_content_disposition(pdf_filename("")) == 'inline; filename="document.pdf"'
    assert safe_content_disposition(pdf_filename('"""')) == 'inline; filename="document.pdf"'


@pytest.mark.parametrize("hostile", [
    "notice.pdf",
    'a"b.pdf',
    "a\r\nX-Evil: 1.pdf",
    "../../etc/passwd.pdf",
    "测试文档.pdf",
    "Zulassungsprüfung.pdf",
    "a;b\\c/d.pdf",
    "\x00\x01\x1f.pdf",
    "",
    "..",
    "🙂.pdf",
    "a" * 500 + ".pdf",
])
def test_output_is_always_latin1_encodable(hostile):
    """The invariant that keeps the ASGI layer from raising on a valid document."""
    for disposition in ("inline", "attachment"):
        value = safe_content_disposition(hostile, disposition)
        value.encode("latin-1")  # raises UnicodeEncodeError on regression
        assert value.startswith(f'{disposition}; filename="')

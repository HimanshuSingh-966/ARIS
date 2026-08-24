"""
api/utils.py
Pure helpers shared across routes. No I/O, no framework coupling — safe to unit test.
"""

import re
import unicodedata
from urllib.parse import quote

# Control characters (including CR and LF) must never reach a header value: a
# bare newline lets a caller-supplied filename inject arbitrary extra headers.
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")

# `"` would terminate the quoted filename parameter early; `\` would escape the
# terminator. Path separators are dropped so a stored name can't suggest a path.
_HEADER_UNSAFE = re.compile(r'[";\\/\r\n]')


def pdf_filename(doc_name: str, fallback: str = "document") -> str:
    """
    Turn a stored doc_name into a .pdf filename, without doubling the extension.

    doc_name is written by ingestor.list_b2_files as basename-minus-".pdf", but
    that is not enforced anywhere, so handle a name that already carries it.
    """
    name = (doc_name or "").strip()
    if not name:
        return f"{fallback}.pdf"
    if name.lower().endswith(".pdf"):
        return name
    return f"{name}.pdf"


def _to_ascii(text: str) -> str:
    """Fold to ASCII, keeping base letters (Ü -> U) rather than dropping them."""
    folded = unicodedata.normalize("NFKD", text)
    return folded.encode("ascii", "ignore").decode("ascii").strip()


def safe_content_disposition(
    filename: str,
    disposition: str = "inline",
    fallback: str = "document",
) -> str:
    """
    Build a Content-Disposition value that cannot corrupt or inject headers.

    Interpolating a database value straight into this header is unsafe on three
    counts: a CR/LF injects new headers, a double quote truncates the filename
    parameter, and any non-Latin-1 character makes the ASGI server raise while
    encoding the response (a 500 on an otherwise valid document).

    Produces an ASCII-safe `filename=` for universal compatibility plus, when the
    name genuinely contains non-ASCII, an RFC 5987 `filename*=UTF-8''…` so modern
    clients still receive the real name.

    Note the extended form is built from the *sanitised* name, not the raw input.
    Percent-encoding would otherwise make a stripped character header-safe while
    still handing the original back to any client that decodes it — so `a"b.pdf`
    would arrive as `a"b.pdf` again.

    Args:
        filename:    desired filename, extension included
        disposition: "inline" or "attachment"
        fallback:    stem used when sanitising leaves nothing usable

    Returns:
        A complete header value, e.g. `inline; filename="notice.pdf"`
    """
    if disposition not in ("inline", "attachment"):
        raise ValueError(f"invalid disposition: {disposition!r}")

    # Sanitise once, keeping non-ASCII: this is the canonical safe name that both
    # the ASCII fallback and the extended form derive from.
    cleaned = _CONTROL_CHARS.sub("", filename or "")
    cleaned = _HEADER_UNSAFE.sub("", cleaned).strip()

    # Leading dots would leave "..", "../" remnants as the visible filename. But a
    # leading dot also means there is no stem: '.pdf' is an extension, not a name.
    # Folding the remainder into the stem position is how a name composed entirely
    # of stripped characters ('""".pdf') came back out as filename="pdf".
    had_leading_dot = cleaned.startswith(".")
    cleaned = cleaned.lstrip(".").strip()

    # Split before folding so that a stem which folds away to nothing (an all-CJK
    # name, say) falls back to a real stem instead of promoting the extension into
    # the filename — otherwise "测试文档.pdf" renders as filename="pdf".
    if "." in cleaned:
        stem, _, ext = cleaned.rpartition(".")
    elif had_leading_dot:
        stem, ext = "", cleaned
    else:
        stem, ext = cleaned, ""

    ascii_stem = _to_ascii(stem) or fallback
    ascii_ext = _to_ascii(ext)
    ascii_name = f"{ascii_stem}.{ascii_ext}" if ascii_ext else ascii_stem

    value = f'{disposition}; filename="{ascii_name}"'

    # The extended form is the same name before ASCII folding — rebuilt from the
    # split parts, not from `cleaned`, so it inherits the fallback stem too.
    unicode_name = f"{stem or fallback}.{ext}" if ext else (stem or fallback)

    # Only add it when it actually carries more information.
    if unicode_name != ascii_name:
        value += f"; filename*=UTF-8''{quote(unicode_name, safe='')}"

    return value

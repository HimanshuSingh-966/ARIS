"""
tests/test_forms_filter.py

Covers api/routes/forms._matches().

The search branch of GET /forms used to ignore `type` and `source` entirely, so
"search within Manufacturing" searched every category: the category chip stayed
highlighted in the UI while the results contradicted it. The listing branch got
those filters for free in SQL; this helper is what brings the RPC-backed search
branch back in line with it.
"""

import pytest

from api.routes.forms import _matches

FORM = {"id": 1, "form_type": "Manufacturing", "source": "cdsco"}


def test_no_filters_matches_everything():
    assert _matches(FORM, None, None) is True
    assert _matches({}, None, None) is True


def test_type_filter():
    assert _matches(FORM, "Manufacturing", None) is True
    assert _matches(FORM, "Import", None) is False


def test_source_filter():
    assert _matches(FORM, None, "cdsco") is True
    assert _matches(FORM, None, "fda") is False


def test_filters_are_conjunctive():
    assert _matches(FORM, "Manufacturing", "cdsco") is True
    assert _matches(FORM, "Manufacturing", "fda") is False
    assert _matches(FORM, "Import", "cdsco") is False


@pytest.mark.parametrize("row", [
    {"id": 1},                                    # column absent
    {"id": 1, "form_type": None, "source": None},  # present but NULL
])
def test_missing_or_null_columns_do_not_match_a_filter(row):
    """`or ""` rather than a bare .get(): a NULL form_type must fail a filter, not
    raise while comparing None to a string."""
    assert _matches(row, "Manufacturing", None) is False
    assert _matches(row, None, "cdsco") is False
    assert _matches(row, None, None) is True


def test_matching_is_exact_not_substring():
    assert _matches({"form_type": "Manufacturing"}, "Manufact", None) is False


def test_empty_string_filters_are_ignored():
    """Falsy filters mean 'unset' — an empty query param must not exclude rows that
    legitimately have a value."""
    assert _matches(FORM, "", "") is True

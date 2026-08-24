"""
tests/test_classify_section.py

Covers pipeline/ingestor.classify_section().

These rules drive the browse-by-section UI, and a false positive misfiles a
document permanently. The previous implementation used bare substring tests, so
`"ct" in hint` matched "impa-ct", "produ-ct", "pra-ct-ice" and "prote-ct-ion" —
which filed most of the corpus under "clinical-trials". Every entry in the
"general" block below is one of those false positives.

Note the boundaries cannot be \b: these strings are filenames and B2 keys where
tokens are separated by - _ . / and space, and \b treats `_` as a word character
(so \btrial\b would miss "clinical_trial").
"""

import pytest

from pipeline.ingestor import classify_section


@pytest.mark.parametrize("hint, expected", [
    # ── the substring-matching false positives ────────────────────────────────
    ("impact-assessment.pdf",        "general"),   # 'act' inside 'impact'
    ("factsheet-2024.pdf",           "general"),   # 'act' inside 'fact'
    ("compact-summary.pdf",          "general"),   # 'act' inside 'compact'
    ("products-list.pdf",            "general"),   # 'ct' inside 'product'
    ("protection-notes.pdf",         "general"),   # 'ct' inside 'protection'
    ("good-practice-manual.pdf",     "general"),   # 'ct'/'act' inside 'practice'
    ("industrial-hygiene.pdf",       "general"),   # 'trial' inside 'industrial'

    # ── guidance-documents ────────────────────────────────────────────────────
    ("drugs-and-cosmetics-act-1940.pdf",  "guidance-documents"),
    ("cdsco/guidance-for-industry.pdf",   "guidance-documents"),
    ("ema-guideline-q1.pdf",              "guidance-documents"),
    ("medical-device-rules-2017.pdf",     "guidance-documents"),

    # ── clinical-trials ───────────────────────────────────────────────────────
    ("CT-01-application.pdf",             "clinical-trials"),
    ("clinical_trial_protocol.pdf",       "clinical-trials"),  # the `_` case \b breaks
    ("fda/clinical-holds.pdf",            "clinical-trials"),
    ("trials-registry.pdf",               "clinical-trials"),

    # ── the rest ──────────────────────────────────────────────────────────────
    ("medical-device-listing.pdf",        "medical-devices"),
    ("in-vitro-diagnostic-kits.pdf",      "medical-devices"),
    ("marketing-authorisation.pdf",       "drug-approvals"),
    ("new_drug-dossier.pdf",              "drug-approvals"),
    ("510k-clearance-letter.pdf",         "drug-approvals"),
    ("warning-letter-2023.pdf",           "compliance-enforcement"),
    ("inspection-report.pdf",             "compliance-enforcement"),
    ("banned-substances.pdf",             "compliance-enforcement"),
    ("cosmetic-labelling.pdf",            "cosmetics"),
    ("biologicals-handbook.pdf",          "biologicals-vaccines"),
    ("vaccine-cold-chain.pdf",            "biologicals-vaccines"),
    ("blood-bank-standards.pdf",          "biologicals-vaccines"),
    ("notification-gsr-123.pdf",          "notifications-advisories"),
    ("advisories-2024.pdf",               "notifications-advisories"),
])
def test_classify_section(hint, expected):
    assert classify_section(hint) == expected


def test_classification_is_case_insensitive():
    assert classify_section("WARNING-LETTER.PDF") == "compliance-enforcement"


@pytest.mark.parametrize("hint", ["", None, "   ", "x.pdf"])
def test_unclassifiable_falls_back_to_general(hint):
    assert classify_section(hint) == "general"


def test_first_rule_wins():
    """Order is load-bearing: it preserves the original if/elif priority, so a name
    matching both 'rules' and 'trial' files under guidance-documents."""
    assert classify_section("clinical-trial-rules.pdf") == "guidance-documents"

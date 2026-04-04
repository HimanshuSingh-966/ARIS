"""
pipeline/form_classifier.py
Categorizes regulatory forms based on keywords in their title and rule references.
"""

import re

# Classification categories and their associated keywords/numbers
FORM_CATEGORIES = {
    "Manufacturing": {
        "keywords": ["manufacture", "repacking", "loan licence", "new drug manufacture"],
        "numbers": ["12", "13", "24A", "25", "25A", "26", "26A", "26B", "26C", "26F", "26H", "26J", "27", "27A", "28", "28A", "CT-21", "CT-22", "CT-23", "CT-26", "CT-27"]
    },
    "Import / Export": {
        "keywords": ["import", "export", "foreign manufacturer", "registration certificate"],
        "numbers": ["8", "8A", "9", "10", "10A", "24", "40", "41", "42", "43", "CT-16", "CT-17", "CT-18", "CT-19", "CT-20", "CT-24", "CT-25"]
    },
    "Wholesale / Retail": {
        "keywords": ["wholesale", "retail", "sale of drugs", "dispensary"],
        "numbers": ["18", "19A", "19B", "20", "20A", "20B"]
    },
    "Clinical Trial": {
        "keywords": ["clinical trial", "new drug approval", "BA/BE study", "ethics committee"],
        "numbers": ["CT-01", "CT-02", "CT-03", "CT-04", "CT-05", "CT-06", "CT-07", "CT-08", "CT-09", "CT-10", "CT-11", "CT-12", "CT-13", "CT-14", "CT-15"]
    },
    "Testing / Analysis": {
        "keywords": ["test", "analysis", "laboratory", "government analyst", "sample submission"],
        "numbers": ["1", "2", "11", "29", "30", "39"]
    },
    "Blood Bank / Biologics": {
        "keywords": ["blood bank", "blood centre", "blood components", "transfusion", "processing unit", "vaccines"],
        "numbers": ["21", "21A", "21B", "21C", "21CC"]
    },
    "Traditional Medicine": {
        "keywords": ["homoeopathic", "ayurvedic", "unani", "siddha"],
        "numbers": ["31", "31A", "32", "32A", "33", "33A", "34"]
    },
    "Cosmetics": {
        "keywords": ["cosmetics", "manufacture cosmetics"],
        "numbers": ["22", "23"]
    },
    "Registration": {
        "keywords": ["registration", "certificate of registration"],
        "numbers": ["40", "41", "42", "43"]
    }
}

def classify_form(form_number: str, title: str) -> str:
    """
    Returns a form category based on form number and title keywords.
    """
    form_number = str(form_number).upper().replace("FORM", "").strip()
    title = title.lower()

    # 1. Direct number check (most accurate)
    for category, rules in FORM_CATEGORIES.items():
        if form_number in rules["numbers"]:
            return category

    # 2. Keyword check
    for category, rules in FORM_CATEGORIES.items():
        if any(kw in title for kw in rules["keywords"]):
            return category

    # 3. Pattern based check
    if form_number.startswith("CT-"):
        return "Clinical Trial"

    return "General"

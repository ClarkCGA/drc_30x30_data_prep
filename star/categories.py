"""Red List category normalisation and STAR weights."""
import pandas as pd

# Older Red List (pre-2001) categories that still appear in some records.
LEGACY_CATEGORIES = {
    "LR/NT": "NT",
    "LR/CD": "NT",  # conservation dependent: treated as Near Threatened by IUCN
    "LR/LC": "LC",
}

VALID = {"EX", "EW", "CR", "EN", "VU", "NT", "LC", "DD"}


def normalise_category(cat):
    if cat is None or (isinstance(cat, float) and pd.isna(cat)):
        return None
    c = str(cat).strip().upper()
    c = LEGACY_CATEGORIES.get(c, c)
    if c.startswith("CR"):  # e.g. "CR(PE)", "CR (PEW)"
        c = "CR"
    return c if c in VALID else None


def weight_of(cat, weights):
    """STAR weight for a normalised category; None if the species is not scored."""
    return weights.get(cat) if cat is not None else None

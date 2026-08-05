"""GeoSignal AI — Candidate placement constraints (Task 30).

Provides:
    HIGH_CANOPY_LAND_COVER_CLASSES         Canonical ESA WorldCover class set.
    CANOPY_HEIGHT_EXCLUSION_THRESHOLD_M    Canonical height threshold.
    is_high_canopy()                       Deforestation exclusion predicate.

This is the SINGLE canonical definition of the deforestation constraint.
Import only from here — do NOT redefine these constants or this function
anywhere else in the codebase.

Requirements: 4.3, 9.2

Deforestation constraint
------------------------
A grid cell or candidate site is classified as high-canopy (excluded from
BTS placement recommendations) when BOTH conditions hold:

    land_cover_class in HIGH_CANOPY_LAND_COVER_CLASSES
    canopy_height_m  >= CANOPY_HEIGHT_EXCLUSION_THRESHOLD_M

Neither condition alone is sufficient.

When rank_bts_candidates is implemented (Task 11–12), it must call
is_high_canopy() with default exclude_high_canopy=True and set
excluded_by_canopy=True on any candidate that is filtered out.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Canonical constants
# ---------------------------------------------------------------------------

#: ESA WorldCover 2021 land-cover class codes indicating forested or shrubland
#: terrain that must be excluded from BTS placement recommendations.
#: Class 10 = Tree cover; Class 20 = Shrubland.
HIGH_CANOPY_LAND_COVER_CLASSES: frozenset[int] = frozenset({10, 20})

#: Minimum canopy height in metres for the joint exclusion condition.
#: A site must have BOTH a matching land-cover class AND canopy height
#: at or above this threshold to be excluded.
CANOPY_HEIGHT_EXCLUSION_THRESHOLD_M: float = 15.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_high_canopy(land_cover_class: int, canopy_height_m: float) -> bool:
    """Return True when a site meets the joint deforestation exclusion condition.

    A site is classified high-canopy (excluded from BTS placement) if and
    only if BOTH of the following hold:

        land_cover_class in HIGH_CANOPY_LAND_COVER_CLASSES   ({10, 20})
        canopy_height_m  >= CANOPY_HEIGHT_EXCLUSION_THRESHOLD_M  (15.0 m)

    Examples:
        >>> is_high_canopy(10, 15.0)   # Tree cover, exactly at threshold → True
        True
        >>> is_high_canopy(10, 14.9)   # Tree cover, below threshold → False
        False
        >>> is_high_canopy(30, 20.0)   # Cropland, above threshold → False
        False
        >>> is_high_canopy(20, 20.0)   # Shrubland, above threshold → True
        True

    Args:
        land_cover_class: ESA WorldCover class code for the cell.
        canopy_height_m:  Canopy height in metres for the cell.

    Returns:
        bool — True if the site should be excluded from recommendations.

    Requirements: 4.3, 9.2
    """
    return (
        land_cover_class in HIGH_CANOPY_LAND_COVER_CLASSES
        and canopy_height_m >= CANOPY_HEIGHT_EXCLUSION_THRESHOLD_M
    )

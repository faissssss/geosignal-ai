"""Environmental constraints for BTS candidate selection.

This module contains the canonical high-canopy exclusion rule used by the
Recommendation Engine before BTS candidates are ranked.
"""

from __future__ import annotations

from collections.abc import Set


# ESA WorldCover classes treated as woody/tree-cover candidates.
#
# 10 = Tree cover
# 20 = Shrubland
#
# A class in this set is not excluded automatically. The canopy-height
# threshold must also be met.
HIGH_CANOPY_LAND_COVER_CLASSES: frozenset[int] = frozenset({10, 20})


# Default canopy-height threshold above which a candidate may require
# meaningful vegetation clearing.
CANOPY_HEIGHT_EXCLUSION_THRESHOLD_M: float = 15.0


def is_high_canopy(
    land_cover_class: int,
    canopy_height_m: float,
    *,
    high_canopy_classes: Set[int] = HIGH_CANOPY_LAND_COVER_CLASSES,
    threshold_m: float = CANOPY_HEIGHT_EXCLUSION_THRESHOLD_M,
) -> bool:
    """Return whether a BTS candidate must be excluded for high canopy.

    A candidate is classified as high-canopy only when both conditions hold:

    1. Its ESA WorldCover class is included in ``high_canopy_classes``.
    2. Its canopy height is greater than or equal to ``threshold_m``.

    Parameters
    ----------
    land_cover_class:
        ESA WorldCover integer class code.

    canopy_height_m:
        Canopy height in metres.

    high_canopy_classes:
        Configurable set of land-cover classes considered for exclusion.
        Defaults to tree cover and shrubland: ``{10, 20}``.

    threshold_m:
        Configurable canopy-height threshold in metres. Defaults to 15 metres.

    Returns
    -------
    bool
        ``True`` only when both the land-cover and canopy-height conditions
        are satisfied.
    """
    return (
        land_cover_class in high_canopy_classes
        and canopy_height_m >= threshold_m
    )
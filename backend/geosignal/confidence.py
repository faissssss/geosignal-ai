"""GeoSignal AI — Confidence_Tagger.

Single canonical implementation of tag_confidence, used for heatmap cells,
BTS candidates, and drag-and-drop outputs.  Do NOT redefine ConfidenceThresholds
here — it is imported from geosignal.models.
"""
from __future__ import annotations

import math

from geosignal.models import ConfidenceThresholds


def tag_confidence(
    point: tuple[float, float],
    nearest_opencellid_km: float | None,
    nearest_ookla_km: float | None,
    thresholds: ConfidenceThresholds,
) -> str:
    """Assign a confidence tag based on data-source proximity.

    Parameters
    ----------
    point:
        (lat, lon) of the cell or candidate being tagged.  Accepted for API
        symmetry; not used in the distance logic itself.
    nearest_opencellid_km:
        Distance to the nearest OpenCellID record in km.
        Pass ``None`` or ``float("inf")`` when no record exists within the
        search radius.  Absence of a record is NOT treated as confirmed zero
        coverage.
    nearest_ookla_km:
        Distance to the nearest Ookla measurement tile in km.
        Same absence semantics as ``nearest_opencellid_km``.
    thresholds:
        Imported ``ConfidenceThresholds`` instance (single canonical definition
        lives in ``geosignal.models``).

    Returns
    -------
    str
        One of ``"High"``, ``"Med"``, or ``"Low"``.

    Rules (implemented precisely; property test checks if-and-only-if logic)
    -------------------------------------------------------------------------
    Treat ``None`` and ``float("inf")`` as "record absent".

    High : opencellid_km < high_km  AND  ookla_km < high_km

    Low  : opencellid_km > low_km  AND  ookla_km > low_km
           OR either value is absent (None / inf)
           Note: "absent" means value is None, math.isinf(value), or
           value > low_km.  The OR-absent clause dominates — if *either*
           source is absent the result is always Low.

    Med  : everything else (exactly one within high_km but not both;
           or both between high_km and low_km inclusive).
    """
    # Normalise absence: None and inf both become float("inf")
    def _normalise(v: float | None) -> float:
        if v is None:
            return math.inf
        return float(v)

    ocid = _normalise(nearest_opencellid_km)
    ookla = _normalise(nearest_ookla_km)

    high = thresholds.high_km
    low = thresholds.low_km

    # A value is "absent within low_km" if it is inf, NaN-like, or > low_km.
    # We treat isinf as the canonical absent marker after normalisation.
    ocid_absent = math.isinf(ocid)
    ookla_absent = math.isinf(ookla)

    # Low: either source absent, or both strictly beyond low_km
    if ocid_absent or ookla_absent:
        return "Low"
    if ocid > low and ookla > low:
        return "Low"

    # High: both strictly within high_km
    if ocid < high and ookla < high:
        return "High"

    # Med: everything else
    return "Med"

"""Tests for GeoSignal AI environmental candidate constraints."""

from geosignal.constraints import (
    CANOPY_HEIGHT_EXCLUSION_THRESHOLD_M,
    HIGH_CANOPY_LAND_COVER_CLASSES,
    is_high_canopy,
)


def test_tree_cover_below_threshold_is_not_excluded() -> None:
    """Tree cover with 14.9 m canopy does not meet the height condition."""
    assert is_high_canopy(
        land_cover_class=10,
        canopy_height_m=14.9,
    ) is False


def test_tree_cover_at_threshold_is_excluded() -> None:
    """Tree cover at exactly 15.0 m satisfies both exclusion conditions."""
    assert is_high_canopy(
        land_cover_class=10,
        canopy_height_m=15.0,
    ) is True


def test_shrubland_above_threshold_is_excluded() -> None:
    """Shrubland with tall woody cover satisfies both conditions."""
    assert is_high_canopy(
        land_cover_class=20,
        canopy_height_m=20.0,
    ) is True


def test_non_high_canopy_class_above_threshold_is_not_excluded() -> None:
    """Canopy height alone must not exclude a non-target land-cover class."""
    assert is_high_canopy(
        land_cover_class=40,
        canopy_height_m=20.0,
    ) is False


def test_land_cover_class_alone_does_not_exclude() -> None:
    """A target land-cover class still requires canopy height >= threshold."""
    assert is_high_canopy(
        land_cover_class=20,
        canopy_height_m=5.0,
    ) is False


def test_custom_canopy_threshold_is_supported() -> None:
    """A region-specific threshold can override the default configuration."""
    assert is_high_canopy(
        land_cover_class=10,
        canopy_height_m=12.0,
        threshold_m=10.0,
    ) is True


def test_custom_land_cover_classes_are_supported() -> None:
    """A region-specific land-cover set can override the default classes."""
    assert is_high_canopy(
        land_cover_class=30,
        canopy_height_m=18.0,
        high_canopy_classes=frozenset({30}),
    ) is True


def test_default_constants_match_design_specification() -> None:
    """Default constants must remain aligned with the design document."""
    assert HIGH_CANOPY_LAND_COVER_CLASSES == frozenset({10, 20})
    assert CANOPY_HEIGHT_EXCLUSION_THRESHOLD_M == 15.0
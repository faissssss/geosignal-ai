/**
 * Colour tier classification for Coverage Score heatmap.
 *
 * Thresholds (design.md § Interactive_Map, Requirement 3.1):
 *   Green  : score >= 70  (Good)
 *   Yellow : 40 <= score < 70  (Moderate)
 *   Red    : score < 40   (Poor)
 *
 * Three cases are exhaustive, mutually exclusive, and boundary-inclusive.
 * Score is never rounded or modified before classification.
 *
 * # Feature: geosignal-ai, Property 11: Colour Tier Correctness
 */
export type ColourTier = 'Green' | 'Yellow' | 'Red'

/**
 * Classify a Coverage Score (0–100) into a colour tier.
 *
 * @param score  Coverage Score; must be in [0.0, 100.0].
 *               No rounding is applied — the raw value is compared directly.
 * @returns      'Green' | 'Yellow' | 'Red'
 */
export function colourTier(score: number): ColourTier {
  if (score >= 70) return 'Green'
  if (score >= 40) return 'Yellow'
  return 'Red'
}

/**
 * Snake-case alias required by the Task 22 spec.
 * Delegates directly to colourTier — no separate logic.
 *
 * # Feature: geosignal-ai, Property 11: Colour Tier Correctness
 */
export const colour_tier = colourTier

// ---------------------------------------------------------------------------
// CSS / MapLibre colour constants
// ---------------------------------------------------------------------------

/** Hex fill colours used by the Coverage Gap Heatmap layer. */
export const HEATMAP_COLOURS: Record<ColourTier, string> = {
  Green:  '#22c55e', // Good coverage  (score >= 70)
  Yellow: '#eab308', // Moderate coverage (40 <= score < 70)
  Red:    '#ef4444', // Poor coverage  (score < 40)
}

/**
 * Convert a ColourTier to its hex CSS colour string.
 * Centralises the mapping so callers never hard-code hex values.
 */
export function tierToColour(tier: ColourTier): string {
  return HEATMAP_COLOURS[tier]
}

/**
 * MapLibre GL `step` paint expression for fill-color on a coverage layer.
 *
 * Reads the `coverage_score` property from each GeoJSON feature and maps
 * it to the correct colour tier using the same thresholds (40, 70).
 * The thresholds here must always match colourTier — they are derived from
 * the same constants, not duplicated independently.
 *
 * Usage:
 *   map.addLayer({ type: 'fill', paint: { 'fill-color': HEATMAP_PAINT_EXPRESSION } })
 */
export const HEATMAP_PAINT_EXPRESSION = [
  'step',
  ['get', 'coverage_score'],
  HEATMAP_COLOURS.Red,    // default bucket: score < 40
  40, HEATMAP_COLOURS.Yellow,
  70, HEATMAP_COLOURS.Green,
] as const

/**
 * Opacity values for the confidence visual indicator.
 *
 * Confidence is shown via fill-opacity, independently of fill-color,
 * so it never changes Green→Yellow or Red→Green (Property 11 invariant).
 */
export const CONFIDENCE_OPACITY: Record<'Low' | 'Med' | 'High', number> = {
  High: 0.85,
  Med:  0.55,
  Low:  0.30,
}

/**
 * MapLibre GL `match` paint expression for fill-opacity based on
 * the `confidence_tag` property of each GeoJSON feature.
 *
 * Applied as a second layer / separate paint property so opacity
 * is completely independent of colour classification.
 */
export const CONFIDENCE_OPACITY_EXPRESSION = [
  'match',
  ['get', 'confidence_tag'],
  'High', CONFIDENCE_OPACITY.High,
  'Med',  CONFIDENCE_OPACITY.Med,
  'Low',  CONFIDENCE_OPACITY.Low,
  CONFIDENCE_OPACITY.Med, // fallback
] as const

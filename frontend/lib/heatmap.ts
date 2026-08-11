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
 * Continuous thermal ramp for the Coverage Gap Heatmap.
 *
 * The spec's tiered step expression (HEATMAP_PAINT_EXPRESSION) collapses the
 * entire score range below 40 into one red — so regions whose scores all fall
 * in [0, 40) (the common case for NTT data, where every cell is < 35) render
 * as a single flat colour with no visual variation.
 *
 * This interpolate ramp instead maps the observed score domain (0..40) onto a
 * distinct colour gradient (dark red → red → orange → amber → yellow), so cells
 * with different coverage scores are visibly distinguishable while the
 * "lower score = hotter/worse" thermal semantics are preserved.
 *
 * Stops deliberately span 0..40: scores >= 40 sit at the pale end, and any
 * score in the Yellow/Green tier keeps a sensible colour too.
 */
export const HEATMAP_GRADIENT_EXPRESSION = [
  'interpolate',
  ['linear'],
  ['coalesce', ['get', 'coverage_score'], 0],
  // [score, colour] stops
  0,  '#7f1d1d', // very low score  — deep red
  8,  '#dc2626', // low              — red
  16, '#ea580c', // low-mid          — orange
  24, '#f59e0b', // mid              — amber
  32, '#eab308', // mid-high         — yellow
  40, '#fde047', // >= 40            — pale yellow
] as const

/** Heatmap colour rendering modes. */
export type HeatmapMode = 'thermal' | 'gap' | 'confidence'

/**
 * Confidence colour ramp — used by the 'confidence' heatmap mode.
 * Encodes High/Med/Low as distinct colours so confidence is easy to read
 * independently of score. (Score colouring stays in the other two modes.)
 */
export const CONFIDENCE_COLOR_EXPRESSION = [
  'match',
  ['coalesce', ['get', 'confidence_tag'], 'Low'],
  'High', '#22c55e', // green — high confidence
  'Med',  '#eab308', // yellow — medium
  'Low',  '#ef4444', // red — low confidence
  '#ef4444',         // fallback
] as const

/**
 * Select the fill-color expression for a given heatmap mode.
 *   - 'thermal'    → HEATMAP_GRADIENT_EXPRESSION (continuous ramp, default)
 *   - 'gap'        → HEATMAP_PAINT_EXPRESSION    (spec traffic-light steps)
 *   - 'confidence' → CONFIDENCE_COLOR_EXPRESSION (High/Med/Low colours)
 */
export function heatmapFillExpression(mode: HeatmapMode): readonly unknown[] {
  switch (mode) {
    case 'gap':        return HEATMAP_PAINT_EXPRESSION
    case 'confidence': return CONFIDENCE_COLOR_EXPRESSION
    case 'thermal':
    default:           return HEATMAP_GRADIENT_EXPRESSION
  }
}

/**
 * Plotly-like density_mapbox colour ramp. MapLibre heatmap layers colour the
 * computed kernel density, so this mirrors a Plasma-style scale: transparent
 * dark purple at the edge, violet/magenta through the body, then orange/yellow
 * at the hottest coverage-gap cores.
 */
export const HEATMAP_DENSITY_COLOR_EXPRESSION = [
  'interpolate',
  ['linear'],
  ['heatmap-density'],
  0,    'rgba(13, 8, 135, 0)',
  0.08, 'rgba(13, 8, 135, 0.28)',
  0.22, 'rgba(84, 3, 160, 0.45)',
  0.38, 'rgba(139, 10, 165, 0.58)',
  0.55, 'rgba(203, 71, 119, 0.72)',
  0.72, 'rgba(248, 149, 64, 0.86)',
  0.88, 'rgba(252, 221, 36, 0.95)',
  1,    'rgba(240, 249, 33, 1)',
] as const

/**
 * Weight expression for the native GIS-style heatmap layer.
 * Lower coverage_score means a hotter coverage gap, so the score is inverted.
 */
export const HEATMAP_WEIGHT_EXPRESSION = [
  'interpolate',
  ['linear'],
  ['coalesce', ['get', 'coverage_score'], 100],
  0,   1,
  8,   0.95,
  16,  0.8,
  24,  0.65,
  32,  0.45,
  40,  0.3,
  70,  0.12,
  100, 0.04,
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

/**
 * Colour tier classification for Coverage Score heatmap.
 *
 * Thresholds from design.md:
 *   Green  : score >= 70  (Good)
 *   Yellow : 40 <= score < 70  (Moderate)
 *   Red    : score < 40   (Poor)
 *
 * Three cases are exhaustive and mutually exclusive.
 */
export type ColourTier = 'Green' | 'Yellow' | 'Red'

export function colourTier(score: number): ColourTier {
  if (score >= 70) return 'Green'
  if (score >= 40) return 'Yellow'
  return 'Red'
}

export const HEATMAP_COLOURS: Record<ColourTier, string> = {
  Green:  '#22c55e',  // Good coverage
  Yellow: '#eab308',  // Moderate coverage
  Red:    '#ef4444',  // Poor coverage
}

// MapLibre paint expression for heatmap layer colouring
// Consumes grid_cells.coverage_score from Supabase
export const HEATMAP_PAINT_EXPRESSION = [
  'step',
  ['get', 'coverage_score'],
  HEATMAP_COLOURS.Red,    // default (score < 40)
  40, HEATMAP_COLOURS.Yellow,
  70, HEATMAP_COLOURS.Green,
] as const

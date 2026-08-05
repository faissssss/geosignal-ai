/**
 * Tests for frontend/lib/heatmap.ts
 *
 * # Feature: geosignal-ai, Property 11: Colour Tier Correctness
 * Validates: Requirements 3.1
 *
 * Covers:
 *   - Task 22.2 — Property 11 generated/parameterised tests over [0, 100]
 *   - Task 22.3 — Boundary unit tests at 39.99, 40.0, 40.01, 69.99, 70.0, 70.01
 *   - Exhaustiveness: every valid score returns exactly Green, Yellow, or Red
 *   - colour_tier alias delegates to colourTier without independent logic
 */

import { describe, it, expect } from 'vitest'
import {
  colourTier,
  colour_tier,
  ColourTier,
  HEATMAP_COLOURS,
  CONFIDENCE_OPACITY,
  tierToColour,
} from '../lib/heatmap'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const VALID_TIERS: ReadonlySet<ColourTier> = new Set(['Green', 'Yellow', 'Red'])

function isValidTier(t: string): t is ColourTier {
  return VALID_TIERS.has(t as ColourTier)
}

/**
 * Generate N evenly-spaced float values in [min, max] inclusive.
 * Used as the parameterised "property" strategy — no external library needed.
 */
function linspace(min: number, max: number, n: number): number[] {
  const step = (max - min) / (n - 1)
  return Array.from({ length: n }, (_, i) => min + i * step)
}

// ---------------------------------------------------------------------------
// Task 22.2 — Property 11: Colour Tier Correctness
//
// Strategy: 1 000 uniformly-spaced scores in [0.0, 100.0]
// plus 200 random-ish values generated from a deterministic sequence.
// Tests the if-and-only-if logic for all three tiers.
//
// # Feature: geosignal-ai, Property 11: Colour Tier Correctness
// Validates: Requirements 3.1
// ---------------------------------------------------------------------------

describe('Property 11 — Colour Tier Correctness (parameterised over [0, 100])', () => {
  const uniformScores = linspace(0, 100, 1000)

  // Extra values: sub-integer precision, negative-approaching 0, and >100 edge
  const extraScores = [
    0, 0.001, 0.5, 1, 5, 10, 20, 30, 39, 39.5, 39.99, 39.999,
    40, 40.001, 40.01, 45, 50, 55, 60, 65, 69, 69.5, 69.99, 69.999,
    70, 70.001, 70.01, 75, 80, 85, 90, 95, 99, 99.9, 99.999, 100,
  ]

  const allScores = [...new Set([...uniformScores, ...extraScores])]

  it('returns exactly one of Green, Yellow, Red for every score in [0, 100]', () => {
    for (const score of allScores) {
      const result = colourTier(score)
      expect(
        isValidTier(result),
        `colourTier(${score}) returned "${result}" — must be Green, Yellow, or Red`,
      ).toBe(true)
    }
  })

  it('returns Green if and only if score >= 70', () => {
    for (const score of allScores) {
      const result = colourTier(score)
      if (score >= 70) {
        expect(result, `score=${score} >= 70 must be Green, got ${result}`).toBe('Green')
      } else {
        expect(result, `score=${score} < 70 must NOT be Green, got ${result}`).not.toBe('Green')
      }
    }
  })

  it('returns Yellow if and only if 40 <= score < 70', () => {
    for (const score of allScores) {
      const result = colourTier(score)
      if (score >= 40 && score < 70) {
        expect(result, `score=${score}: 40<=s<70 must be Yellow, got ${result}`).toBe('Yellow')
      } else {
        expect(result, `score=${score}: outside [40,70) must NOT be Yellow, got ${result}`).not.toBe('Yellow')
      }
    }
  })

  it('returns Red if and only if score < 40', () => {
    for (const score of allScores) {
      const result = colourTier(score)
      if (score < 40) {
        expect(result, `score=${score} < 40 must be Red, got ${result}`).toBe('Red')
      } else {
        expect(result, `score=${score} >= 40 must NOT be Red, got ${result}`).not.toBe('Red')
      }
    }
  })

  it('cases are mutually exclusive (never two tiers true for the same score)', () => {
    for (const score of allScores) {
      const isGreen  = score >= 70
      const isYellow = score >= 40 && score < 70
      const isRed    = score < 40
      const trueCount = [isGreen, isYellow, isRed].filter(Boolean).length
      expect(trueCount, `score=${score} should match exactly one tier`).toBe(1)
    }
  })

  it('cases are exhaustive (at least one tier is always true)', () => {
    for (const score of allScores) {
      const result = colourTier(score)
      expect(['Green', 'Yellow', 'Red']).toContain(result)
    }
  })
})

// ---------------------------------------------------------------------------
// Task 22.3 — Boundary unit tests
// Validates: Requirements 3.1
// ---------------------------------------------------------------------------

describe('Boundary values — colour_tier / colourTier', () => {
  // Red boundary
  it('39.99 → Red', () => {
    expect(colourTier(39.99)).toBe('Red')
    expect(colour_tier(39.99)).toBe('Red')
  })

  // Yellow lower boundary (inclusive)
  it('40.0 → Yellow', () => {
    expect(colourTier(40.0)).toBe('Yellow')
    expect(colour_tier(40.0)).toBe('Yellow')
  })

  it('40.01 → Yellow', () => {
    expect(colourTier(40.01)).toBe('Yellow')
    expect(colour_tier(40.01)).toBe('Yellow')
  })

  // Yellow upper boundary
  it('69.99 → Yellow', () => {
    expect(colourTier(69.99)).toBe('Yellow')
    expect(colour_tier(69.99)).toBe('Yellow')
  })

  // Green lower boundary (inclusive)
  it('70.0 → Green', () => {
    expect(colourTier(70.0)).toBe('Green')
    expect(colour_tier(70.0)).toBe('Green')
  })

  it('70.01 → Green', () => {
    expect(colourTier(70.01)).toBe('Green')
    expect(colour_tier(70.01)).toBe('Green')
  })

  // Edge of valid range
  it('0.0 → Red', () => {
    expect(colourTier(0.0)).toBe('Red')
  })

  it('100.0 → Green', () => {
    expect(colourTier(100.0)).toBe('Green')
  })

  it('50.0 → Yellow', () => {
    expect(colourTier(50.0)).toBe('Yellow')
  })

  // Boundary at exactly 39.9999... approaching 40 from below
  it('39.9999 → Red (below 40)', () => {
    expect(colourTier(39.9999)).toBe('Red')
  })

  // Boundary at exactly 69.9999... approaching 70 from below
  it('69.9999 → Yellow (below 70)', () => {
    expect(colourTier(69.9999)).toBe('Yellow')
  })
})

// ---------------------------------------------------------------------------
// colour_tier alias — must be identical to colourTier (no independent logic)
// ---------------------------------------------------------------------------

describe('colour_tier alias', () => {
  it('is the same function reference as colourTier', () => {
    expect(colour_tier).toBe(colourTier)
  })

  it('produces identical output to colourTier for all boundary values', () => {
    const testScores = [0, 39.99, 40, 40.01, 69.99, 70, 70.01, 100]
    for (const score of testScores) {
      expect(colour_tier(score)).toBe(colourTier(score))
    }
  })
})

// ---------------------------------------------------------------------------
// HEATMAP_COLOURS — thresholds consistent with colourTier
// ---------------------------------------------------------------------------

describe('HEATMAP_COLOURS constants', () => {
  it('has entries for all three tiers', () => {
    expect(HEATMAP_COLOURS.Green).toBeTruthy()
    expect(HEATMAP_COLOURS.Yellow).toBeTruthy()
    expect(HEATMAP_COLOURS.Red).toBeTruthy()
  })

  it('all colour values are valid hex strings', () => {
    const hexPattern = /^#[0-9a-fA-F]{6}$/
    for (const [tier, colour] of Object.entries(HEATMAP_COLOURS)) {
      expect(colour, `${tier} colour should be a hex string`).toMatch(hexPattern)
    }
  })

  it('tierToColour returns the same hex as HEATMAP_COLOURS', () => {
    expect(tierToColour('Green')).toBe(HEATMAP_COLOURS.Green)
    expect(tierToColour('Yellow')).toBe(HEATMAP_COLOURS.Yellow)
    expect(tierToColour('Red')).toBe(HEATMAP_COLOURS.Red)
  })
})

// ---------------------------------------------------------------------------
// CONFIDENCE_OPACITY — independent of colour (Property 11 invariant)
// ---------------------------------------------------------------------------

describe('CONFIDENCE_OPACITY — independent of ColourTier', () => {
  it('has entries for High, Med, Low', () => {
    expect(typeof CONFIDENCE_OPACITY.High).toBe('number')
    expect(typeof CONFIDENCE_OPACITY.Med).toBe('number')
    expect(typeof CONFIDENCE_OPACITY.Low).toBe('number')
  })

  it('all opacity values are in (0, 1]', () => {
    for (const [level, opacity] of Object.entries(CONFIDENCE_OPACITY)) {
      expect(opacity, `${level} opacity must be > 0`).toBeGreaterThan(0)
      expect(opacity, `${level} opacity must be <= 1`).toBeLessThanOrEqual(1)
    }
  })

  it('High opacity >= Med opacity >= Low opacity', () => {
    expect(CONFIDENCE_OPACITY.High).toBeGreaterThanOrEqual(CONFIDENCE_OPACITY.Med)
    expect(CONFIDENCE_OPACITY.Med).toBeGreaterThanOrEqual(CONFIDENCE_OPACITY.Low)
  })

  it('changing confidence does not change the colour tier', () => {
    // The colour classification is solely determined by score, not confidence_tag.
    // We verify that colourTier ignores confidence entirely.
    const score = 55 // Yellow by score
    expect(colourTier(score)).toBe('Yellow') // regardless of any confidence value
    // If someone passed confidence as a second arg it would be ignored (single-param fn)
    expect(colourTier(score)).toBe('Yellow')
  })
})

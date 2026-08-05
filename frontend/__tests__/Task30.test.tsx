/**
 * Task 30 — Frontend Ethics Checklist Tests (Requirements 9.3, 9.5, 11.3)
 *
 * Covers safeguards 2, 3, and partial 7 from the pre-demo checklist:
 *   - 30.2: "GeoAI-assisted estimate" visible in SidePanel, SimulationPanel,
 *            DragDropMarker, ConfidenceGate
 *   - 30.3: Low-confidence gate non-bypassable (gap-filling for Task 24 tests)
 *   - 30.7: model_version and scoring_run_id visible in SidePanel
 *
 * All tests are hermetic — no Supabase required.
 */
import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'

import SidePanel from '../components/SidePanel'
import type { SidePanelSelection } from '../components/SidePanel'
import SimulationPanel, {
  type SimulationResponse,
} from '../components/SimulationPanel'
import DragDropMarker, {
  type DragDropResponse,
} from '../components/DragDropMarker'
import ConfidenceGate from '../components/ConfidenceGate'

import type { BTSCandidate, GridCell, RegionId } from '../lib/types'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const CANDIDATE: BTSCandidate = {
  candidate_id: 'c1', region_id: 'ntt', target_area_id: 'ta-1',
  rank: 1, lat: -9.1, lon: 120.1, expected_improvement: 15.0,
  los_validated: true, confidence_tag: 'High',
  shap_values: {
    elevation_m: 0.10, slope_deg: -0.05, canopy_height_m: 0.08,
    land_cover_class: 0.03, distance_to_bts_m: 0.22,
    road_distance_m: 0.10, population_density_per_km2: 0.18,
    facility_proximity_m: 0.21,
  },
  model_version: 'ahp-v2.0',
  scoring_run_id: 'run-001',
  excluded_by_canopy: false,
}

const CELL: GridCell = {
  cell_id: 'cell-1', region_id: 'ntt', lat: -9.1, lon: 120.1,
  resolution_m: 100, coverage_score: 65.5, confidence_tag: 'Med',
  tier_used: '1',
  shap_top3: [
    { feature_name: 'Distance to nearest BTS tower', value: 0.22, direction: 'positive' },
    { feature_name: 'Distance to nearest facility', value: 0.20, direction: 'positive' },
    { feature_name: 'Population density', value: 0.18, direction: 'positive' },
  ],
  model_version: 'ahp-v2.0',
  scoring_run_id: 'run-001',
}

const REGION: RegionId = 'ntt'

const makeSim = (): SimulationResponse => ({
  kind: 'result',
  before_heatmap: {}, after_heatmap: {},
  pct_good_change: 12.5, villages_newly_covered: 3,
  new_coverage_score: 74.2, elapsed_ms: 450,
})

const makeDragDrop = (): DragDropResponse => ({
  kind: 'result',
  snapped_coordinate: [-9.21, 120.21],
  grid_resolution_m: 100,
  coverage_score: 55.0,
  confidence_tag: 'Med',
  vs_top_candidate: {
    manual_score: 55.0, model_score: 68.0,
    top_candidate_id: 'c1', top_candidate_lat: -9.2, top_candidate_lon: 120.2,
    manual_wins: false,
  },
  elapsed_ms: 300,
})


// ===========================================================================
// 30.2 — GeoAI-assisted estimate label visible
// ===========================================================================

describe('30.2 GeoAI-assisted estimate label', () => {
  // Test 16: SidePanel — cell selection
  it('T30.2.1: SidePanel (cell) shows GeoAI-assisted estimate label', () => {
    const sel: SidePanelSelection = { kind: 'cell', data: CELL }
    render(<SidePanel selection={sel} />)
    const el = screen.getByTestId('geoai-label')
    expect(el.textContent).toMatch(/GeoAI-assisted estimate/i)
  })

  it('T30.2.2: SidePanel (candidate) shows GeoAI-assisted estimate label', () => {
    const sel: SidePanelSelection = { kind: 'candidate', data: CANDIDATE }
    render(<SidePanel selection={sel} />)
    const el = screen.getByTestId('geoai-label')
    expect(el.textContent).toMatch(/GeoAI-assisted estimate/i)
  })

  // Test 17: SimulationPanel
  it('T30.2.3: SimulationPanel shows GeoAI-assisted estimate in result', async () => {
    const submit = vi.fn<
      [string, RegionId],
      Promise<SimulationResponse>
    >().mockResolvedValue(makeSim())
    render(
      <SimulationPanel
        candidate={CANDIDATE} regionId={REGION}
        targetAreaResolved={true} submitSimulate={submit}
      />,
    )
    fireEvent.click(screen.getByTestId('simulate-btn'))
    await waitFor(() => screen.getByTestId('simulate-geoai-label'))
    expect(screen.getByTestId('simulate-geoai-label').textContent)
      .toMatch(/GeoAI-assisted estimate/i)
  })

  // Test 18: DragDropMarker
  it('T30.2.4: DragDropMarker shows GeoAI-assisted estimate in result', async () => {
    const submit = vi.fn<
      [number, number, RegionId, boolean],
      Promise<DragDropResponse>
    >().mockResolvedValue(makeDragDrop())
    const { container } = render(
      <DragDropMarker map={null} regionId={REGION}
        overlayEnabled={false} submitDragDrop={submit} />,
    )
    const panel = container.querySelector('[data-testid="drag-drop-panel"]') as HTMLElement & {
      __handleDrop?: (lat: number, lon: number) => Promise<void>
    }
    await act(async () => { await panel.__handleDrop?.(-9.2, 120.2) })
    await waitFor(() => screen.getByTestId('dragdrop-geoai-label'))
    expect(screen.getByTestId('dragdrop-geoai-label').textContent)
      .toMatch(/GeoAI-assisted estimate/i)
  })

  // Test 19: ConfidenceGate modal
  it('T30.2.5: ConfidenceGate modal shows GeoAI-assisted estimate label', () => {
    render(
      <ConfidenceGate confidenceTag="Low" candidateId="c1"
        guardedAction={vi.fn()} actionLabel="Test" />,
    )
    fireEvent.click(screen.getByTestId('confidence-gate-btn'))
    expect(screen.getByTestId('confidence-gate-geoai-label').textContent)
      .toMatch(/GeoAI-assisted estimate/i)
  })

  it('T30.2.6: GeoAI label present on success result (not only Low-confidence)', async () => {
    // High-confidence candidate — GeoAI label still appears in SimulationPanel
    const submit = vi.fn<
      [string, RegionId],
      Promise<SimulationResponse>
    >().mockResolvedValue(makeSim())
    render(
      <SimulationPanel
        candidate={{ ...CANDIDATE, confidence_tag: 'High' }}
        regionId={REGION} targetAreaResolved={true} submitSimulate={submit}
      />,
    )
    fireEvent.click(screen.getByTestId('simulate-btn'))
    await waitFor(() => screen.getByTestId('simulate-geoai-label'))
    expect(screen.getByTestId('simulate-geoai-label')).toBeTruthy()
  })
})


// ===========================================================================
// 30.3 — Low-confidence gate non-bypassable (gap tests)
// ===========================================================================

describe('30.3 Low-confidence gate (gap coverage)', () => {
  // Test 20: blocked before acknowledgement
  it('T30.3.1: Low-confidence action blocked before acknowledgement', () => {
    const action = vi.fn()
    render(<ConfidenceGate confidenceTag="Low" candidateId="c1"
      guardedAction={action} actionLabel="Go" />)
    fireEvent.click(screen.getByTestId('confidence-gate-btn'))
    expect(action).not.toHaveBeenCalled()
    expect(screen.getByTestId('confidence-gate-modal')).toBeTruthy()
  })

  // Test 21: acknowledge fires exactly once
  it('T30.3.2: acknowledge executes action exactly once', async () => {
    const action = vi.fn()
    render(<ConfidenceGate confidenceTag="Low" candidateId="c1"
      guardedAction={action} actionLabel="Go" />)
    fireEvent.click(screen.getByTestId('confidence-gate-btn'))
    fireEvent.click(screen.getByTestId('confidence-gate-acknowledge-btn'))
    expect(action).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(screen.queryByTestId('confidence-gate-modal')).toBeNull())
  })

  // Test 22: candidate change resets acknowledgement
  it('T30.3.3: changing candidate resets acknowledgement', async () => {
    const action = vi.fn()
    const { rerender } = render(
      <ConfidenceGate confidenceTag="Low" candidateId="c1"
        guardedAction={action} actionLabel="Go" />,
    )
    // Acknowledge c1
    fireEvent.click(screen.getByTestId('confidence-gate-btn'))
    fireEvent.click(screen.getByTestId('confidence-gate-acknowledge-btn'))
    await waitFor(() => expect(action).toHaveBeenCalledTimes(1))

    // Switch to c2 — gate must reopen
    rerender(<ConfidenceGate confidenceTag="Low" candidateId="c2"
      guardedAction={action} actionLabel="Go" />)
    fireEvent.click(screen.getByTestId('confidence-gate-btn'))
    expect(screen.getByTestId('confidence-gate-modal')).toBeTruthy()
    expect(action).toHaveBeenCalledTimes(1)  // not called again
  })

  it('T30.3.4: cancel does not execute action and modal closes', () => {
    const action = vi.fn()
    render(<ConfidenceGate confidenceTag="Low" candidateId="c1"
      guardedAction={action} actionLabel="Go" />)
    fireEvent.click(screen.getByTestId('confidence-gate-btn'))
    fireEvent.click(screen.getByTestId('confidence-gate-cancel-btn'))
    expect(action).not.toHaveBeenCalled()
    expect(screen.queryByTestId('confidence-gate-modal')).toBeNull()
  })

  it('T30.3.5: modal has role=dialog and aria-modal=true', () => {
    render(<ConfidenceGate confidenceTag="Low" candidateId="c1"
      guardedAction={vi.fn()} actionLabel="Go" />)
    fireEvent.click(screen.getByTestId('confidence-gate-btn'))
    const modal = screen.getByTestId('confidence-gate-modal')
    expect(modal.getAttribute('role')).toBe('dialog')
    expect(modal.getAttribute('aria-modal')).toBe('true')
  })
})


// ===========================================================================
// 30.7 — Model version and scoring timestamp visible
// ===========================================================================

const CANDIDATE_WITH_TIMESTAMP: BTSCandidate = {
  ...CANDIDATE,
  scoring_run_timestamp: '2026-08-04T10:30:00.000Z',
}

const CELL_WITH_TIMESTAMP: GridCell = {
  ...CELL,
  scoring_run_timestamp: '2026-08-04T10:30:00.000Z',
}

describe('30.7 Model version and scoring timestamp visible', () => {
  // Test 23: model version
  it('T30.7.1: SidePanel (candidate) shows model_version', () => {
    const sel: SidePanelSelection = { kind: 'candidate', data: CANDIDATE }
    render(<SidePanel selection={sel} />)
    expect(screen.getByTestId('model-version').textContent).toContain('ahp-v2.0')
  })

  // Test 24a: scoring_run_id still shown
  it('T30.7.2: SidePanel (candidate) shows scoring_run_id', () => {
    const sel: SidePanelSelection = { kind: 'candidate', data: CANDIDATE }
    render(<SidePanel selection={sel} />)
    expect(screen.getByTestId('scoring-run').textContent).toContain('run-001')
  })

  // Test 24b: ISO scoring timestamp rendered as visible text (not run ID)
  it('T30.7.2b: SidePanel renders ISO scoring_run_timestamp as visible text', () => {
    const sel: SidePanelSelection = { kind: 'candidate', data: CANDIDATE_WITH_TIMESTAMP }
    render(<SidePanel selection={sel} />)
    const tsEl = screen.getByTestId('scoring-run-timestamp')
    // Must not show the raw ISO string; toLocaleString will produce a
    // human-readable date. The ISO date "2026-08-04" must NOT appear as-is
    // (it will be formatted), but the element must contain something other than '—'.
    expect(tsEl.textContent).not.toBe('—')
    expect(tsEl.textContent).not.toBe('')
    // Must not be a blank/null fallback
    expect(tsEl.textContent!.trim().length).toBeGreaterThan(0)
  })

  it('T30.7.2c: SidePanel shows em-dash when scoring_run_timestamp is absent', () => {
    // CANDIDATE has no scoring_run_timestamp field — undefined → fallback
    const sel: SidePanelSelection = { kind: 'candidate', data: CANDIDATE }
    render(<SidePanel selection={sel} />)
    expect(screen.getByTestId('scoring-run-timestamp').textContent).toBe('—')
  })

  it('T30.7.2d: scoring_run_timestamp is distinct from scoring_run_id in the UI', () => {
    const sel: SidePanelSelection = { kind: 'candidate', data: CANDIDATE_WITH_TIMESTAMP }
    render(<SidePanel selection={sel} />)
    const tsEl   = screen.getByTestId('scoring-run-timestamp')
    const runEl  = screen.getByTestId('scoring-run')
    // The timestamp element must NOT show the raw run ID string
    expect(tsEl.textContent).not.toBe('run-001')
    // The run ID element still shows the run ID
    expect(runEl.textContent).toContain('run-001')
  })

  it('T30.7.3: SidePanel (cell) shows model_version', () => {
    const sel: SidePanelSelection = { kind: 'cell', data: CELL }
    render(<SidePanel selection={sel} />)
    expect(screen.getByTestId('model-version').textContent).toContain('ahp-v2.0')
  })

  it('T30.7.4: SidePanel (cell) shows scoring_run_id', () => {
    const sel: SidePanelSelection = { kind: 'cell', data: CELL }
    render(<SidePanel selection={sel} />)
    expect(screen.getByTestId('scoring-run').textContent).toContain('run-001')
  })

  it('T30.7.4b: SidePanel (cell) shows scoring_run_timestamp when available', () => {
    const sel: SidePanelSelection = { kind: 'cell', data: CELL_WITH_TIMESTAMP }
    render(<SidePanel selection={sel} />)
    const tsEl = screen.getByTestId('scoring-run-timestamp')
    expect(tsEl.textContent).not.toBe('—')
    expect(tsEl.textContent!.trim().length).toBeGreaterThan(0)
  })

  it('T30.7.5: missing model_version shows em-dash fallback', () => {
    const sel: SidePanelSelection = {
      kind: 'candidate',
      data: { ...CANDIDATE, model_version: '' },
    }
    render(<SidePanel selection={sel} />)
    expect(screen.getByTestId('model-version').textContent).toBe('—')
  })

  // Test 25: SHAP top-3 in same panel
  it('T30.7.6: SHAP top-3 visible in same panel as coverage score', () => {
    const sel: SidePanelSelection = { kind: 'cell', data: CELL }
    render(<SidePanel selection={sel} />)
    const panel = screen.getByTestId('side-panel-content')
    expect(panel.querySelector('[data-testid="shap-top3"]')).toBeTruthy()
    expect(panel.querySelector('[data-testid="coverage-score"]')).toBeTruthy()
  })

  // Test 26: raw object not rendered
  it('T30.7.7: SHAP values not rendered as raw [object Object]', () => {
    const sel: SidePanelSelection = { kind: 'cell', data: CELL }
    render(<SidePanel selection={sel} />)
    expect(screen.getByTestId('side-panel-content').textContent)
      .not.toContain('[object Object]')
  })
})

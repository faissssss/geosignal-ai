/**
 * Tests for LayersButton component — plan Phase 5.
 *
 * Covers:
 *  1. Button opens/closes panel
 *  2. All six overlay toggles render and call onVisibilityChange
 *  3. Base map radios render; unavailable options are disabled
 *  4. Coverage mode radios call onCoverageModeChange
 *  5. Heatmap opacity slider calls onHeatmapOpacityChange
 *  6. Legend toggle calls onShowLegendChange
 *  7. Escape closes the panel
 */

import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import LayersButton from '../components/LayersButton'
import type { LayerVisibility } from '../lib/types'

const VISIBILITY: LayerVisibility = {
  heatmap:    true,
  landcover:  true,
  contours:   true,
  villages:   true,
  btsMarkers: true,
  candidates: true,
}

function renderLayersButton(overrides: Partial<Parameters<typeof LayersButton>[0]> = {}) {
  const props = {
    visibility: VISIBILITY,
    onVisibilityChange: vi.fn(),
    baseMapMode: 'default' as const,
    onBaseMapModeChange: vi.fn(),
    coverageMode: 'thermal' as const,
    onCoverageModeChange: vi.fn(),
    heatmapOpacity: 1,
    onHeatmapOpacityChange: vi.fn(),
    showLegend: true,
    onShowLegendChange: vi.fn(),
    ...overrides,
  }
  return render(<LayersButton {...props} />)
}

function openPanel() {
  fireEvent.click(screen.getByTestId('layers-button'))
}

describe('LayersButton — open/close', () => {
  it('panel is hidden by default', () => {
    renderLayersButton()
    expect(screen.queryByTestId('layers-panel')).toBeNull()
  })

  it('button click opens the panel and sets aria-expanded', () => {
    renderLayersButton()
    const button = screen.getByTestId('layers-button')
    expect(button.getAttribute('aria-expanded')).toBe('false')
    openPanel()
    expect(screen.getByTestId('layers-panel')).toBeTruthy()
    expect(button.getAttribute('aria-expanded')).toBe('true')
  })

  it('second click closes the panel', () => {
    renderLayersButton()
    openPanel()
    expect(screen.getByTestId('layers-panel')).toBeTruthy()
    openPanel()
    expect(screen.queryByTestId('layers-panel')).toBeNull()
  })

  it('Escape closes an open panel', () => {
    renderLayersButton()
    openPanel()
    expect(screen.getByTestId('layers-panel')).toBeTruthy()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByTestId('layers-panel')).toBeNull()
  })
})

describe('LayersButton — overlay toggles', () => {
  it('renders all six layer toggles', () => {
    renderLayersButton()
    openPanel()
    const keys: Array<keyof LayerVisibility> = [
      'heatmap', 'landcover', 'contours', 'villages', 'btsMarkers', 'candidates',
    ]
    keys.forEach((k) => {
      expect(screen.getByTestId(`layer-option-${k}`)).toBeTruthy()
    })
  })

  it('calls onVisibilityChange when a toggle is clicked', () => {
    const onVisibilityChange = vi.fn()
    renderLayersButton({ onVisibilityChange })
    openPanel()
    fireEvent.click(screen.getByTestId('layers-checkbox-heatmap'))
    expect(onVisibilityChange).toHaveBeenCalledWith('heatmap', false)
  })

  it('reflects the visibility prop', () => {
    renderLayersButton({
      visibility: { ...VISIBILITY, contours: false },
    })
    openPanel()
    const contours = screen.getByTestId('layers-checkbox-contours') as HTMLInputElement
    expect(contours.checked).toBe(false)
    const heatmap = screen.getByTestId('layers-checkbox-heatmap') as HTMLInputElement
    expect(heatmap.checked).toBe(true)
  })
})

describe('LayersButton — base map modes', () => {
  it('renders Default / Satellite / Terrain radios', () => {
    renderLayersButton()
    openPanel()
    expect(screen.getByTestId('basemap-radio-default')).toBeTruthy()
    expect(screen.getByTestId('basemap-radio-satellite')).toBeTruthy()
    expect(screen.getByTestId('basemap-radio-terrain')).toBeTruthy()
  })

  it('calls onBaseMapModeChange with the selected mode', () => {
    const onBaseMapModeChange = vi.fn()
    // Start on a non-default mode so clicking Default produces a change event.
    renderLayersButton({ onBaseMapModeChange, baseMapMode: 'terrain' })
    openPanel()
    // default is always available
    fireEvent.click(screen.getByTestId('basemap-radio-default'))
    expect(onBaseMapModeChange).toHaveBeenCalledWith('default')
  })

  it('disables unavailable base map options when no tile URL is configured', () => {
    // Env vars are not set in the test environment, so satellite/terrain are
    // unavailable by default.
    renderLayersButton()
    openPanel()
    expect((screen.getByTestId('basemap-radio-default') as HTMLInputElement).disabled).toBe(false)
    expect((screen.getByTestId('basemap-radio-satellite') as HTMLInputElement).disabled).toBe(true)
    expect((screen.getByTestId('basemap-radio-terrain') as HTMLInputElement).disabled).toBe(true)
  })
})

describe('LayersButton — coverage visualization modes', () => {
  it('renders Thermal / Gaps / Confidence radios', () => {
    renderLayersButton()
    openPanel()
    expect(screen.getByTestId('coverage-radio-thermal')).toBeTruthy()
    expect(screen.getByTestId('coverage-radio-gap')).toBeTruthy()
    expect(screen.getByTestId('coverage-radio-confidence')).toBeTruthy()
  })

  it('calls onCoverageModeChange when a mode is selected', () => {
    const onCoverageModeChange = vi.fn()
    renderLayersButton({ onCoverageModeChange })
    openPanel()
    fireEvent.click(screen.getByTestId('coverage-radio-confidence'))
    expect(onCoverageModeChange).toHaveBeenCalledWith('confidence')
  })
})

describe('LayersButton — display options', () => {
  it('calls onHeatmapOpacityChange when the slider moves', () => {
    const onHeatmapOpacityChange = vi.fn()
    renderLayersButton({ onHeatmapOpacityChange, heatmapOpacity: 1 })
    openPanel()
    fireEvent.change(screen.getByTestId('heatmap-opacity-slider'), { target: { value: '0.5' } })
    expect(onHeatmapOpacityChange).toHaveBeenCalledWith(0.5)
  })

  it('calls onShowLegendChange when the legend checkbox toggles', () => {
    const onShowLegendChange = vi.fn()
    renderLayersButton({ onShowLegendChange })
    openPanel()
    fireEvent.click(screen.getByTestId('legend-checkbox'))
    expect(onShowLegendChange).toHaveBeenCalledWith(false)
  })
})

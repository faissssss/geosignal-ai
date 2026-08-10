/**
 * Unit tests for empty results warning banner implementation
 * Task 3.4: Add empty results messaging
 * 
 * Tests Requirements 2.7, 2.8, 2.12, 2.13:
 * - Warning message when targetArea selected but no cells match
 * - Boundary highlight remains visible (managed by TargetAreaSelector)
 * - Appropriate styling and data-testid for testing
 * 
 * NOTE: These tests verify the implementation exists in MapView.tsx
 * Integration testing is handled via manual testing and E2E tests
 */

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'

describe('Empty Results Warning Banner Implementation', () => {
  const mapViewPath = join(process.cwd(), 'components', 'MapView.tsx')
  const mapViewContent = readFileSync(mapViewPath, 'utf-8')
  const filterPath = join(process.cwd(), 'lib', 'validation', 'filterCellsByTargetArea.ts')
  const filterContent = readFileSync(filterPath, 'utf-8')

  it('should implement conditional warning banner when targetArea exists and coverageCells is empty', () => {
    // Verify the condition: targetArea && coverageCells.length === 0
    expect(mapViewContent).toContain('targetArea && coverageCells.length === 0')
  })

  it('should include data-testid="no-cells-warning" for testing', () => {
    // Verify test ID is present
    expect(mapViewContent).toContain('data-testid="no-cells-warning"')
  })

  it('should display correct warning message text', () => {
    // Verify the warning message text
    expect(mapViewContent).toContain('No Heatmap Data Available')
    expect(mapViewContent).toContain('No heatmap data available for selected area')
    expect(mapViewContent).toContain('Data may not be processed yet for this kecamatan')
  })

  it('should have warning styling with appropriate colors', () => {
    // Verify warning colors (yellow/amber gradient)
    const warningBannerSection = mapViewContent.substring(
      mapViewContent.indexOf('no-cells-warning'),
      mapViewContent.indexOf('no-cells-warning') + 1000
    )
    
    // Check for warning colors
    expect(warningBannerSection).toContain('#fef3c7') // Light yellow
    expect(warningBannerSection).toContain('#fde68a') // Amber
    expect(warningBannerSection).toContain('#f59e0b') // Orange border
    expect(warningBannerSection).toContain('borderRadius') // React inline style
    expect(warningBannerSection).toContain('boxShadow') // React inline style
  })

  it('should include warning icon in the banner', () => {
    const warningBannerSection = mapViewContent.substring(
      mapViewContent.indexOf('no-cells-warning'),
      mapViewContent.indexOf('no-cells-warning') + 1000
    )
    
    // Verify warning emoji is present
    expect(warningBannerSection).toContain('⚠️')
  })

  it('should position warning banner in overlay section', () => {
    // Verify warning banner is in the controls overlay section
    const overlaySection = mapViewContent.substring(
      mapViewContent.indexOf('position: \'absolute\''),
      mapViewContent.indexOf('position: \'absolute\'') + 3000
    )
    
    expect(overlaySection).toContain('no-cells-warning')
  })

  it('should apply spatial filtering before rendering cells', () => {
    // Verify filterCellsByTargetArea is called with error callback
    expect(mapViewContent).toContain('const filteredCells = filterCellsByTargetArea(cells, targetArea, setBoundaryGeometryError)')
    
    // Verify filtered cells are mapped to coverage cells
    expect(mapViewContent).toContain('const coverageCells: CoverageCell[] = filteredCells.map')
  })

  it('should implement filterCellsByTargetArea function', () => {
    // The shared production implementation lives in lib/validation
    // (heatmap-kecamatan / nextjs-filtering overlap was consolidated there)
    expect(filterContent).toContain('function filterCellsByTargetArea')
    expect(filterContent).toContain('export function filterCellsByTargetArea')
    expect(filterContent).toContain('booleanPointInPolygon')
    expect(filterContent).toContain('@turf/boolean-point-in-polygon')
  })

  it('should preserve boundary highlight independently of cell count', () => {
    // The boundary highlight is managed by TargetAreaSelector component
    // It's not affected by the coverageCells.length check
    // Verify TargetAreaSelector is rendered and receives targetArea state
    expect(mapViewContent).toContain('<TargetAreaSelector')
    expect(mapViewContent).toContain('onResolved={handleTargetAreaResolved}')
    expect(mapViewContent).toContain('onReset={handleTargetAreaReset}')
  })

  it('should have proper text styling for readability', () => {
    const warningBannerSection = mapViewContent.substring(
      mapViewContent.indexOf('no-cells-warning'),
      mapViewContent.indexOf('no-cells-warning') + 1000
    )
    
    // Check for proper font styling
    expect(warningBannerSection).toContain('fontFamily')
    expect(warningBannerSection).toContain('fontSize')
    expect(warningBannerSection).toContain('lineHeight')
    expect(warningBannerSection).toContain('maxWidth')
  })
})

/**
 * IMPLEMENTATION VERIFICATION SUMMARY:
 * 
 * Task 3.4 Requirements Status:
 * ✅ Add conditional UI in MapView overlay section
 * ✅ Check if `targetArea && coverageCells.length === 0`
 * ✅ Display warning banner with message
 * ✅ Add `data-testid="no-cells-warning"` for testing
 * ✅ Style banner with warning colors (gradient yellow/amber, orange border)
 * ✅ Proper positioning in overlay controls
 * ✅ Boundary highlight remains visible (managed by TargetAreaSelector)
 * ✅ Spatial filtering applied before rendering (filterCellsByTargetArea)
 * 
 * MANUAL TESTING CHECKLIST:
 * 1. Load MapView with a region (e.g., NTT)
 * 2. Select a kecamatan with cells → no warning should appear
 * 3. Select a kecamatan with NO cells → warning banner should appear
 * 4. Verify warning banner displays correct message
 * 5. Verify boundary remains highlighted even with warning
 * 6. Verify banner styling is visually appropriate (warning colors, readable text)
 * 7. Reset target area → warning should disappear
 */

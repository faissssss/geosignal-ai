import MapView from '@/components/MapView'

/**
 * GeoSignal AI — Main page (Task 23).
 * Renders the full Interactive_Map.
 * MapView handles WebGL detection, all layers, SidePanel, RegionSelector,
 * and TargetAreaSelector internally.
 */
export default function Home() {
  return (
    <main style={{ width: '100vw', height: '100vh' }}>
      <MapView initialRegion="ntt" />
    </main>
  )
}

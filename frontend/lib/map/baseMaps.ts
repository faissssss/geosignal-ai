/**
 * Base map (background tile) configurations.
 *
 * Modes:
 *   - 'default'  : OSM raster tiles (always available).
 *   - 'satellite': requires NEXT_PUBLIC_BASEMAP_SATELLITE_URL; when missing the
 *                  option is still rendered but marked unavailable.
 *   - 'terrain'  : requires NEXT_PUBLIC_BASEMAP_TERRAIN_URL; same rule.
 *
 * Centralising the tile URLs here keeps MapView free of hard-coded tile
 * providers and makes switching a single setTiles() call.
 */

export type BaseMapMode = 'default' | 'satellite' | 'terrain'

export const BASE_MAP_MODES: BaseMapMode[] = ['default', 'satellite', 'terrain']

export interface BaseMapConfig {
  id: BaseMapMode
  label: string
  /** Raster tile URL templates, e.g. 'https://tile.openstreetmap.org/{z}/{x}/{y}.png' */
  tiles: string[]
  attribution: string
  /** Whether the tiles are configured and usable right now. */
  available: boolean
  /** Shown when available === false. */
  unavailableHint?: string
}

const SATELLITE_URL = process.env.NEXT_PUBLIC_BASEMAP_SATELLITE_URL
const TERRAIN_URL = process.env.NEXT_PUBLIC_BASEMAP_TERRAIN_URL

export const BASE_MAPS: Record<BaseMapMode, BaseMapConfig> = {
  default: {
    id: 'default',
    label: 'Default',
    tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
    attribution: '© OpenStreetMap contributors',
    available: true,
  },
  satellite: {
    id: 'satellite',
    label: 'Satellite',
    tiles: SATELLITE_URL ? [SATELLITE_URL] : [],
    attribution: SATELLITE_URL ? 'Satellite imagery' : '',
    available: Boolean(SATELLITE_URL),
    unavailableHint: 'Satellite unavailable: configure NEXT_PUBLIC_BASEMAP_SATELLITE_URL',
  },
  terrain: {
    id: 'terrain',
    label: 'Terrain',
    tiles: TERRAIN_URL ? [TERRAIN_URL] : [],
    attribution: TERRAIN_URL ? 'Terrain tiles' : '',
    available: Boolean(TERRAIN_URL),
    unavailableHint: 'Terrain unavailable: configure NEXT_PUBLIC_BASEMAP_TERRAIN_URL',
  },
}

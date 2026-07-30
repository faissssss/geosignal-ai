import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'

export async function POST(request: NextRequest) {
  const body = await request.json()
  const { lat, lon, region_id, overlay_enabled } = body

  if (lat === undefined || lon === undefined || !region_id) {
    return NextResponse.json(
      { error: 'lat, lon, and region_id are required' },
      { status: 400 }
    )
  }

  const supabase = await createClient()

  // Check grid extent — fetch all whatif_grid centroids for this region
  // Full BallTree snap logic runs in the Python backend (Task 20.1).
  // This route stub returns the nearest available row or OutsideExtentError.
  const { data, error } = await supabase
    .from('whatif_grid')
    .select('*')
    .eq('region_id', region_id)
    .limit(100)

  if (error || !data || data.length === 0) {
    return NextResponse.json({
      outside_extent: true,
      dropped_lat: lat,
      dropped_lon: lon,
      region_id,
      message: 'Dropped coordinate is outside the precomputed grid extent.',
    })
  }

  // Find nearest centroid by Euclidean approximation (full haversine BallTree in Python)
  let nearest = data[0]
  let minDist = Infinity
  for (const row of data) {
    const d = Math.hypot(row.snapped_lat - lat, row.snapped_lon - lon)
    if (d < minDist) {
      minDist = d
      nearest = row
    }
  }

  // overlay_enabled must NOT affect coverage_score (Property 14)
  return NextResponse.json({
    ...nearest,
    // overlay_enabled is accepted but coverage_score is unchanged
    overlay_enabled: overlay_enabled ?? false,
  })
}

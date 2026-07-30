import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'

export async function POST(request: NextRequest) {
  const body = await request.json()
  const { region_id, selection_method, payload } = body

  if (!region_id || !selection_method || payload === undefined) {
    return NextResponse.json(
      { error: 'region_id, selection_method, and payload are required' },
      { status: 400 }
    )
  }

  const supabase = await createClient()

  let boundary_geojson = payload
  let kecamatan_id: string | null = null

  if (selection_method === 'kecamatan') {
    kecamatan_id = payload as string
    const { data, error } = await supabase
      .from('admin_boundaries')
      .select('boundary_geojson')
      .eq('kecamatan_id', kecamatan_id)
      .single()

    if (error || !data) {
      return NextResponse.json(
        { error: `Kecamatan '${kecamatan_id}' not found in admin_boundaries` },
        { status: 404 }
      )
    }
    boundary_geojson = data.boundary_geojson
  }

  const target_area_id = crypto.randomUUID()
  const { error: insertError } = await supabase.from('target_areas').insert({
    target_area_id,
    region_id,
    selection_method,
    kecamatan_id,
    boundary_geojson,
  })

  if (insertError) {
    return NextResponse.json({ error: insertError.message }, { status: 500 })
  }

  return NextResponse.json({
    target_area_id,
    region_id,
    selection_method,
    kecamatan_id,
    boundary_geojson,
  })
}

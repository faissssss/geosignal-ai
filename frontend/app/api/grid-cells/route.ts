import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url)
  const region_id = searchParams.get('region_id')
  const resolution_m = searchParams.get('resolution_m')
  const target_area_id = searchParams.get('target_area_id')

  if (!region_id) {
    return NextResponse.json({ error: 'region_id is required' }, { status: 400 })
  }

  const supabase = await createClient()
  let query = supabase
    .from('grid_cells')
    .select('cell_id, lat, lon, coverage_score, confidence_tag, tier_used, shap_top3, model_version, scoring_run_id')
    .eq('region_id', region_id)

  if (resolution_m) {
    query = query.eq('resolution_m', parseInt(resolution_m))
  }

  const { data, error } = await query
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }

  return NextResponse.json(data)
}

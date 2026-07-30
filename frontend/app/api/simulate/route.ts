import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'

export async function POST(request: NextRequest) {
  const body = await request.json()
  const { candidate_id, region_id } = body

  if (!candidate_id || !region_id) {
    return NextResponse.json(
      { error: 'candidate_id and region_id are required' },
      { status: 400 }
    )
  }

  const supabase = await createClient()
  const { data, error } = await supabase
    .from('whatif_grid')
    .select('*')
    .eq('candidate_id', candidate_id)
    .eq('region_id', region_id)
    .single()

  if (error || !data) {
    // Return UnavailableScenario — never interpolate or extrapolate
    return NextResponse.json({
      unavailable: true,
      candidate_id,
      region_id,
      message: 'No precomputed scenario available for this candidate.',
    })
  }

  return NextResponse.json(data)
}

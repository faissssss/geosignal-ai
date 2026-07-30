import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'

export async function POST(request: NextRequest) {
  const body = await request.json()
  const { target_area_id } = body

  if (!target_area_id) {
    return NextResponse.json({ error: 'target_area_id is required' }, { status: 400 })
  }

  const supabase = await createClient()
  const { data, error } = await supabase
    .from('bts_candidates')
    .select('*')
    .eq('target_area_id', target_area_id)
    .order('rank', { ascending: true })

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }

  return NextResponse.json(data)
}

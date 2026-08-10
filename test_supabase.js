// Quick test to verify Supabase connection works
const { createClient } = require('@supabase/supabase-js')
require('dotenv').config()

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_KEY
)

async function test() {
  console.log('Testing Supabase connection...')
  console.log('URL:', process.env.SUPABASE_URL)
  console.log('Service key exists:', !!process.env.SUPABASE_SERVICE_KEY)
  
  try {
    const { data, error } = await supabase
      .from('grid_cells')
      .select('cell_id, region_id, lat, lon, resolution_m, coverage_score')
      .eq('region_id', 'ntt')
      .eq('resolution_m', 100)
      .limit(5)
    
    if (error) {
      console.error('Query error:', error)
    } else {
      console.log('Success! Found', data.length, 'cells')
      console.log('First cell:', data[0])
    }
  } catch (err) {
    console.error('Exception:', err)
  }
}

test()

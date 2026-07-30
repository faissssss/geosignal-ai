export default function Home() {
  return (
    <main
      style={{
        width: '100vw',
        height: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: 'sans-serif',
      }}
    >
      <div style={{ textAlign: 'center' }}>
        <h1>GeoSignal AI</h1>
        <p>Coverage Gap Heatmap &amp; BTS Placement Recommendation</p>
        <p style={{ color: '#888', fontSize: '0.9rem' }}>
          Map component coming in Task 22 — see <code>frontend/lib/heatmap.ts</code> for colour tier logic.
        </p>
      </div>
    </main>
  )
}

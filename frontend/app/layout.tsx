import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'GeoSignal AI',
  description: "GeoAI-Assisted Coverage Gap Detection & BTS Placement Recommendation for Indonesia's 3T Regions",
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body style={{ margin: 0, padding: 0 }}>{children}</body>
    </html>
  )
}

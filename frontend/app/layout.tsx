import type { Metadata } from 'next'
import Script from 'next/script'

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
      <body style={{ margin: 0, padding: 0 }}>
        <Script id="ignore-extension-m-id-error" strategy="beforeInteractive">
          {`
            (function () {
              function isKnownExtensionMIDError(event) {
                var message = String(
                  event && (event.message || (event.reason && event.reason.message)) || ''
                );
                var filename = String(event && event.filename || '');
                return filename.indexOf('chrome-extension://') === 0 && message.indexOf('M_ID') !== -1;
              }

              window.addEventListener('error', function (event) {
                if (!isKnownExtensionMIDError(event)) return;
                event.preventDefault();
                event.stopImmediatePropagation();
              }, true);

              window.addEventListener('unhandledrejection', function (event) {
                if (!isKnownExtensionMIDError(event)) return;
                event.preventDefault();
                event.stopImmediatePropagation();
              }, true);
            })();
          `}
        </Script>
        {children}
      </body>
    </html>
  )
}
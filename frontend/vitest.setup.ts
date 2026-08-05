import '@testing-library/jest-dom'

// jsdom does not implement URL.createObjectURL — maplibre-gl needs this at import time.
if (typeof window !== 'undefined' && !window.URL.createObjectURL) {
  window.URL.createObjectURL = () => 'blob:mock'
  window.URL.revokeObjectURL = () => {}
}

/**
 * WebGL detection utility — Task 23.4
 *
 * Provides a safe, testable check for WebGL 1/2 support.
 * All browser API access is guarded so this module is safe to import
 * in SSR contexts (typeof window check before any DOM access).
 */

/** Result shape returned by detectWebGL. */
export interface WebGLDetectionResult {
  supported: boolean
  /** The specific context type detected, or null when unsupported. */
  contextType: 'webgl2' | 'webgl' | null
  /** Human-readable reason when unsupported. */
  reason?: string
}

/**
 * Detect whether WebGL is available in the current browser environment.
 *
 * - Returns { supported: false } on server-side render (no window/document).
 * - Returns { supported: false } when neither webgl2 nor webgl context can
 *   be created.
 * - Returns { supported: true, contextType } when a context is available.
 *
 * The canvas element created for probing is never attached to the DOM and
 * is discarded after the check.
 *
 * @param canvasFactory  Optional factory for the probe canvas — allows test
 *                       injection without touching the real DOM.
 */
export function detectWebGL(
  canvasFactory?: () => HTMLCanvasElement | null,
): WebGLDetectionResult {
  // Guard: no window in SSR environments
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return {
      supported: false,
      contextType: null,
      reason: 'Server-side rendering — WebGL is not available.',
    }
  }

  try {
    const canvas = canvasFactory
      ? canvasFactory()
      : document.createElement('canvas')

    if (!canvas) {
      return {
        supported: false,
        contextType: null,
        reason: 'Unable to create canvas element for WebGL probe.',
      }
    }

    // Prefer WebGL 2; fall back to WebGL 1.
    const ctx2 = canvas.getContext('webgl2')
    if (ctx2) {
      // Explicitly lose the context to free GPU resources
      const ext = ctx2.getExtension('WEBGL_lose_context')
      ext?.loseContext()
      return { supported: true, contextType: 'webgl2' }
    }

    const ctx1 =
      canvas.getContext('webgl') ??
      canvas.getContext('experimental-webgl' as 'webgl')
    if (ctx1) {
      const ext = (ctx1 as WebGLRenderingContext).getExtension(
        'WEBGL_lose_context',
      )
      ext?.loseContext()
      return { supported: true, contextType: 'webgl' }
    }

    return {
      supported: false,
      contextType: null,
      reason:
        'Your browser does not support WebGL. ' +
        'Please use a current version of Chrome, Firefox, or Edge.',
    }
  } catch (err) {
    return {
      supported: false,
      contextType: null,
      reason: `WebGL detection error: ${String(err)}`,
    }
  }
}

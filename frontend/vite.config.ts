import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server proxies /api to the backend, mirroring the production
// setup where SPA and API share one origin. Same-origin in both
// environments means cookies and CORS behave identically everywhere.
//
// The `test` block configures Vitest. It is typed through vitest/config,
// whose bundled Vite types conflict with this project's Vite 8 (rolldown)
// types, so the property is annotated for the runtime and hidden from tsc —
// Vitest reads the plain object regardless.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  // @ts-expect-error Vitest augments the Vite config; see note above.
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
})

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    strictPort: true,
    // Dev-mode reverse proxy. In development the browser loads the app from
    // Vite (localhost:5174) and calls the API at RELATIVE paths like
    // /api/grid/15. This block forwards those to the backend on :8000 and
    // strips the /api prefix, so the backend sees its real route /grid/15.
    //
    // Why: it makes dev behave EXACTLY like the production nginx container
    // (5.4 part 2), which does the same proxy. One mental model for both, and
    // because everything is same-origin to the browser, CORS stops mattering.
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
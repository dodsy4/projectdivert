import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// In development the app runs on :5173 and the Flask API on :5000. Proxying
// /api keeps the browser on one origin, so there is no CORS setup to get wrong
// and the production build can use same-origin relative URLs unchanged.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_PROXY || 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
    },
  },
  build: { outDir: 'dist', sourcemap: true },
});

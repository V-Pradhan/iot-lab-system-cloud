import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// In development the browser talks to Vite (5173); /api calls are forwarded to FastAPI (8000).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { '/api': 'http://localhost:8000' } },
});

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Backend runs on :8080; the dev server proxies API calls to it.
    proxy: { '/api': 'http://localhost:8080' },
  },
});

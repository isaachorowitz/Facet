import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: '/',
  build: { outDir: 'dist' },
  server: {
    host: '127.0.0.1',
    proxy: {
      '/api': { target: 'http://127.0.0.1:8765' },
      '/ws': { target: 'http://127.0.0.1:8765', ws: true },
      '/video.mjpg': { target: 'http://127.0.0.1:8765' },
    },
  },
});

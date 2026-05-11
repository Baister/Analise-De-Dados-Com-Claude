import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: '/app/',
  build: {
    outDir: '../static',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/auth':   'http://localhost:8765',
      '/dados':  'http://localhost:8765',
      '/status': 'http://localhost:8765',
      '/stream': 'http://localhost:8765',
      '/config': 'http://localhost:8765',
    },
  },
  test: {
    environment: 'jsdom',
  },
});

import { defineConfig } from 'vite';

export default defineConfig({
  preview: {
    host: '127.0.0.1',
    proxy: {
      '/api': { target: process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000', changeOrigin: false },
    },
  },
  server: {
    host: '127.0.0.1',
    proxy: {
      '/api': {
        target: process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
    },
  },
});

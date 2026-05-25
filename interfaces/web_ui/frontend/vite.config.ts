import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/swarm': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/routing': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/nodes': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/settings': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  base: '/static/',
  build: {
    outDir: '../static/react',
    emptyOutDir: true,
  },
})

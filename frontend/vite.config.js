import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const target = 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': target, '/media': target, '/voices': target },
  },
  build: { outDir: 'dist', emptyOutDir: true },
})

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const target = 'http://localhost:8000'

// Start the two latin UI fonts downloading with the HTML instead of after the CSS is parsed (no text jump).
const PRELOAD = [/inter-latin-wght-normal.*\.woff2$/, /bricolage-grotesque-latin-wght-normal.*\.woff2$/]
function preloadFonts() {
  return {
    name: 'preload-fonts',
    transformIndexHtml(html, ctx) {
      if (!ctx.bundle) return html
      const files = Object.keys(ctx.bundle).filter((f) => PRELOAD.some((re) => re.test(f)))
      return {
        html,
        tags: files.map((f) => ({ tag: 'link', injectTo: 'head-prepend',
          attrs: { rel: 'preload', href: `/${f}`, as: 'font', type: 'font/woff2', crossorigin: '' } })),
      }
    },
  }
}

export default defineConfig({
  plugins: [react(), preloadFonts()],
  server: {
    proxy: { '/api': target, '/media': target, '/voices': target },
  },
  build: { outDir: 'dist', emptyOutDir: true },
})

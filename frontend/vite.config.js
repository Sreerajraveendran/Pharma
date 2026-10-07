import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    target: 'es2020',
    rollupOptions: {
      output: {
        // Libraries change less often than app code: separate chunks stay cached across deploys
        manualChunks(id) {
          // Rollup's CommonJS interop helper is shared by React and the charts; keep it with
          // React, or the entry chunk ends up importing (and preloading) the whole charts chunk
          if (id.includes('commonjsHelpers')) return 'react'
          if (!id.includes('node_modules')) return undefined
          if (/[\\/](recharts|d3-[^\\/]+|victory-vendor|internmap|decimal\.js-light)[\\/]/.test(id)) return 'charts'
          if (/[\\/](react|react-dom|scheduler)[\\/]/.test(id)) return 'react'
          if (/[\\/]@tanstack[\\/]/.test(id)) return 'query'
          if (/[\\/]lucide-react[\\/]/.test(id)) return 'icons'
          // Anything else stays with whatever imports it (e.g. chart helpers load with the charts)
          return undefined
        },
      },
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
      }
    }
  }
})

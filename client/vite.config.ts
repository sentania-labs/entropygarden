import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,           // expose to all interfaces (required for Docker)
    port: 5173,
    allowedHosts: true,   // allow any hostname (proxied behind nginx in dev)
  },
})

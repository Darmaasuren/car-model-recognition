import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  const api = new URL(env.VITE_API_BASE_URL)
  const ws = new URL(env.VITE_WS_BASE_URL)
  const apiPath = api.pathname.replace(/\/+$/, '') || '/api'
  const wsPath = ws.pathname.replace(/\/+$/, '') || '/api'
  const proxy = {
    target: api.origin,
    changeOrigin: true,
    ws: true,
  }

  return {
    plugins: [react()],
    server: {
      proxy: {
        [apiPath]: proxy,
        ...(wsPath !== apiPath ? {
          [wsPath]: { target: ws.origin, changeOrigin: true, ws: true },
        } : {}),
        '/media': { target: api.origin, changeOrigin: true },
      },
    },
  }
})

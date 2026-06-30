import { defineConfig } from 'vitest/config'
import { loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const appDir = dirname(fileURLToPath(import.meta.url))
const repoRoot = resolve(appDir, '../..')

function proxyHeaders(token?: string) {
  return token ? { Authorization: `Bearer ${token}` } : undefined
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, repoRoot, '')
  const go2Target = env.OPENCLAW_GO2_URL || 'http://127.0.0.1:18789'
  const tb4Target = env.OPENCLAW_TB4_URL || 'http://127.0.0.1:18789'

  return {
    envDir: repoRoot,
    define: {
      __APP_HOME_DIR__: JSON.stringify(''),
    },
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: 3000,
      proxy: {
        '/api/ai-tb4': {
          target: tb4Target,
          changeOrigin: true,
          headers: proxyHeaders(env.OPENCLAW_TB4_TOKEN),
          rewrite: (path) => path.replace(/^\/api\/ai-tb4/, ''),
        },
        '/api/ai': {
          target: go2Target,
          changeOrigin: true,
          headers: proxyHeaders(env.OPENCLAW_GO2_TOKEN),
          rewrite: (path) => path.replace(/^\/api\/ai/, ''),
        },
      },
    },
    test: {
      globals: true,
      environment: 'jsdom',
    },
  }
})

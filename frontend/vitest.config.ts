import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  test: {
    environment: 'happy-dom',
    environmentOptions: {
      // 以门户地址为测试页面地址，并放行跨端口请求（真实后端在 8000）。
      happyDOM: {
        url: 'http://127.0.0.1:5173/portal/',
        fetch: { disableSameOriginPolicy: true },
      } as never,
    },
    include: ['src/**/*.spec.ts'],
    globals: true,
  },
})

import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 后端地址默认取本文件里写的端口，起服务时可以用 VITE_PROXY_TARGET 覆盖，
// 这样换端口调试或做启动探针时前端不用改代码。
const proxyTarget = process.env.VITE_PROXY_TARGET ?? 'http://127.0.0.1:8000'

const proxy = {
  '/api': { target: proxyTarget, changeOrigin: true },
  '/portal/api': { target: proxyTarget, changeOrigin: true },
}

// 构建产物挂在站点根下（资源在 /assets/...）。页面同时支持两套入口：
//   独立站点根路径 /review_meeting/3
//   教务门户子路径 /portal/review_meeting/3
// 两套入口由前端路由分别解析，互不跳转，这样旧地址里的老师仍被识别为
// 「独立站点」入口，门户里的老师被识别为「教务门户」入口。
// 部署层（server.mjs / vite dev / vite preview）对两套路径都做 SPA 回退。
export default defineConfig({
  base: '/',
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    // 关掉自动打开页面：起服务时只打印地址，不拉起浏览器
    open: false,
    strictPort: false,
    proxy,
  },
  preview: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: false,
    proxy,
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})

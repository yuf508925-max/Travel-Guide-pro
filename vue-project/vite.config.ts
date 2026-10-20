import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    // vueDevTools(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // 把 /api 开头的请求转给 Python 后端，这样前端写 '/api/chat' 就行，
    // 也不用管跨域（CORS）。后端没起时这里会返回 500，属正常。
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,   // 注意大小写：写成 changeorigin 会静默失效
      },
    },
  },
})

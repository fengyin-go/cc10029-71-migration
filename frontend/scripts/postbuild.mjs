/** 构建后处理：为不做 SPA 回退的静态主机补一份 /portal/index.html。 */
import { copyFileSync, existsSync, mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const dist = resolve(root, 'dist')
const index = resolve(dist, 'index.html')

if (!existsSync(index)) {
  console.error('未找到 dist/index.html，请先执行 vite build')
  process.exit(1)
}
const portalDir = resolve(dist, 'portal')
mkdirSync(portalDir, { recursive: true })
copyFileSync(index, resolve(portalDir, 'index.html'))
console.log('已生成 dist/portal/index.html（门户子路径入口）')

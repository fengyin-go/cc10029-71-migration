#!/usr/bin/env node
/**
 * 部署用静态服务器（无第三方依赖）。
 *
 * 迁移期同时提供两套入口，指向同一份构建产物和同一个后端业务实例：
 *
 *   /           独立站点（旧地址，以前收藏的深链继续可用）
 *   /portal/    教务门户子路径
 *
 * - 两套入口都做前端路由回退；
 * - /api 与 /portal/api 反向代理到后端；
 * - /assets 与 /portal/assets 返回同一批静态资源。
 *
 * 环境变量：
 *   PORT           监听端口，默认 5173
 *   HOST           监听地址，默认 0.0.0.0
 *   BACKEND_TARGET 后端地址，默认 http://127.0.0.1:8000
 *   DIST_DIR       构建产物目录，默认 ./dist
 */
import { createReadStream, existsSync, statSync } from 'node:fs'
import { createServer } from 'node:http'
import { request as httpRequest } from 'node:http'
import { request as httpsRequest } from 'node:https'
import { extname, join, normalize, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = resolve(fileURLToPath(new URL('.', import.meta.url)))
const PORT = Number(process.env.PORT ?? 5173)
const HOST = process.env.HOST ?? '0.0.0.0'
const BACKEND = new URL(process.env.BACKEND_TARGET ?? 'http://127.0.0.1:8000')
const DIST = resolve(here, process.env.DIST_DIR ?? 'dist')
const INDEX = join(DIST, 'index.html')

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
  '.map': 'application/json; charset=utf-8',
}

function isApi(pathname) {
  return pathname === '/api' || pathname.startsWith('/api/')
    || pathname === '/portal/api' || pathname.startsWith('/portal/api/')
}

function sendFile(res, filePath) {
  res.setHeader('Content-Type', MIME[extname(filePath)] ?? 'application/octet-stream')
  res.setHeader(
    'Cache-Control',
    filePath === INDEX ? 'no-cache' : 'public, max-age=31536000, immutable',
  )
  createReadStream(filePath).pipe(res)
}

function proxy(req, res) {
  const target = new URL(req.url, BACKEND)
  const transport = target.protocol === 'https:' ? httpsRequest : httpRequest
  const upstream = transport(
    {
      protocol: target.protocol,
      hostname: target.hostname,
      port: target.port,
      path: target.pathname + target.search,
      method: req.method,
      headers: { ...req.headers, host: target.host },
    },
    (upstreamRes) => {
      res.writeHead(upstreamRes.statusCode ?? 502, upstreamRes.headers)
      upstreamRes.pipe(res)
    },
  )
  upstream.on('error', (error) => {
    res.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8' })
    res.end(JSON.stringify({ detail: `后端不可达：${error.message}` }))
  })
  req.pipe(upstream)
}

/** 把 / 与 /portal/ 两套路径映射到同一份构建产物（/assets 与 /portal/assets 等价）。 */
function resolveStatic(pathname) {
  let relative = pathname
  if (relative === '/portal' || relative.startsWith('/portal/')) {
    relative = relative.slice('/portal'.length) || '/'
  }
  const safe = normalize(relative).replace(/^(\.\.[/\\])+/, '')
  const candidate = join(DIST, safe)
  if (!candidate.startsWith(DIST)) return null
  if (existsSync(candidate) && statSync(candidate).isFile()) return candidate
  return null
}

const server = createServer((req, res) => {
  const url = new URL(req.url ?? '/', `http://${req.headers.host ?? 'localhost'}`)
  const pathname = decodeURIComponent(url.pathname)

  if (isApi(pathname)) {
    proxy(req, res)
    return
  }

  const filePath = resolveStatic(pathname)
  if (filePath) {
    sendFile(res, filePath)
    return
  }

  // 门户子路径的深链：优先用构建产物里的 portal/index.html。
  if (pathname === '/portal' || pathname.startsWith('/portal/')) {
    const portalIndex = join(DIST, 'portal', 'index.html')
    if (existsSync(portalIndex)) {
      sendFile(res, portalIndex)
      return
    }
  }

  // 页面导航与旧深链：统一回到 SPA 入口，由前端路由按路径解析入口身份。
  if (existsSync(INDEX)) {
    sendFile(res, INDEX)
    return
  }
  res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' })
  res.end('构建产物不存在，请先执行 npm run build')
})

server.listen(PORT, HOST, () => {
  console.log(`教学诊改协同台已启动：http://${HOST}:${PORT}/portal/`)
  console.log(`独立站点旧地址：http://${HOST}:${PORT}/`)
  console.log(`后端地址：${BACKEND.origin}`)
})

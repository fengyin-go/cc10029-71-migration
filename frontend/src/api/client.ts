/** 统一请求封装：拼后端地址、抛网络错误、给页脚留一句可读的说明。
 *
 * 迁移期两个入口：
 * - 门户（``/portal/...``）调 ``/portal/api/...``；
 * - 独立站点（根路径）调 ``/api/...``。
 * 两条路径在后端指向同一个业务实例，编号完全一致。
 */
import { apiPrefix, currentSite } from './entry'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export const SITE = currentSite()
export const SITE_LABEL = SITE === 'portal' ? '教务门户' : '独立站点'

export { apiPrefix }

/** 把 /api/... 形式按当前入口重写到对应前缀。 */
export function resolveApiPath(path: string): string {
  if (path.startsWith('http')) return path
  const prefix = API_BASE ? API_BASE.replace(/\/$/, '') : apiPrefix()
  if (prefix === '/api') return path
  if (path === '/api' || path.startsWith('/api/')) return `${prefix}${path.slice(4)}`
  return `${prefix}${path}`
}

export function request(path: string, init?: RequestInit): Promise<Response> {
  const url = resolveApiPath(path)
  return fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  }).catch((error: unknown) => {
    const detail = error instanceof Error ? error.message : '请求未送达'
    throw new Error(`接口请求失败：${detail}`)
  })
}

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await request(path)
  if (!response.ok) {
    throw new Error(`接口返回 ${response.status}，数据未更新`)
  }
  return (await response.json()) as T
}

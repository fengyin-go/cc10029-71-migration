/** 入口基址与旧链接兼容：新部署在 /portal/，旧部署和旧收藏仍在根路径。 */

/** 教务门户固定占用 /portal 子路径。 */
const PORTAL_PATH = '/portal'

/** 门户子路径的纯路径部分，固定为 /portal 。 */
export function portalRoot(): string {
  return PORTAL_PATH
}

/** 新入口的地址前缀，固定为 /portal/ 。 */
export function portalBase(): string {
  return `${PORTAL_PATH}/`
}

/** 判断当前页面是不是从旧地址（根路径）打开的。 */
export function isLegacyEntry(pathname: string = window.location.pathname): boolean {
  return !(pathname === PORTAL_PATH || pathname.startsWith(portalBase()))
}

/** 当前入口：门户或独立站点。接口前缀与回执来源都按它决定。 */
export function currentSite(): 'portal' | 'legacy' {
  return isLegacyEntry() ? 'legacy' : 'portal'
}

/** 当前入口对应的接口前缀。 */
export function apiPrefix(): string {
  return isLegacyEntry() ? '/api' : '/portal/api'
}

/** 旧收藏的路径原样保留在根路径，门户路由额外带 /portal 前缀。 */
export function isPortalPath(pathname: string): boolean {
  return pathname === PORTAL_PATH || pathname.startsWith(portalBase())
}

/**
 * 把浏览器路径换成业务路径：去掉门户前缀，其余原样返回。
 * 例如 /portal/review_meeting/3 -> /review_meeting/3 ，/review_meeting/3 不变。
 */
export function stripPortalPrefix(pathname: string): string {
  if (pathname === PORTAL_PATH) return '/'
  if (pathname.startsWith(portalBase())) return '/' + pathname.slice(portalBase().length)
  return pathname
}

/** 在当前入口内跳转：门户入口的站内链接自动带 /portal 前缀。 */
export function siteLink(path: string): string {
  const target = path.startsWith('/') ? path : `/${path}`
  if (isLegacyEntry()) return target
  return target === '/' ? PORTAL_PATH : `${PORTAL_PATH}${target}`
}

/** 切到另一个入口，保留当前页面（deep link 仍指向同一条纪要/任务）。 */
export function switchEntryLink(fullPath: string): string {
  const business = stripPortalPrefix(fullPath.split(/[?#]/)[0])
  const suffix = fullPath.slice(fullPath.split(/[?#]/)[0].length)
  if (isLegacyEntry()) {
    return business === '/' ? `${PORTAL_PATH}/${suffix}` : `${PORTAL_PATH}${business}${suffix}`
  }
  return `${business}${suffix}`
}

/** 当前是不是门户入口。 */
export function inPortal(): boolean {
  return !isLegacyEntry()
}

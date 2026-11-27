/** 纯前端数据层的公共类型：与全栈版后端返回的结构保持一致，换回后端时页面不用改。 */

export type EntryRow = {
  id: number
  status: string
  pending: boolean
  abnormal: boolean
  receipt?: string
  receiptView?: ReceiptView
  taskId?: number
  回执编号?: string
  来源会议?: number
  [field: string]: unknown
}

export type ModuleMeta = {
  key: string
  name: string
  entity: string
  desc: string
  fields: string[]
  statuses: string[]
  actions: string[]
  actionTargets: Record<string, string>
  metrics: string[]
}

export type PageResult = {
  items: EntryRow[]
  total: number
  page: number
  size: number
  instance?: string
}

export type ActionResult = {
  ok: boolean
  message: string
  entry?: EntryRow | null
  status?: string | null
  receipt?: ReceiptView | null
}

export type ReceiptStatus = '已分发' | '可续办' | '尚待原入口处理'

export type ReceiptView = {
  receipt: string
  meetingId: number
  taskId: number | null
  taskStatus: string | null
  status: ReceiptStatus
  distributed: boolean
  canResume: boolean
  awaitingOriginal: boolean
  duplicate: boolean
  claimed: boolean
  originSite: string
  originSiteLabel: string
  sites: string[]
  requestCount: number
  lastError: string
  storeInstance: string
  message: string
  requester?: string | null
  receipts?: ReceiptView[]
}

export type OverviewResult = {
  cards: { label: string; value: number }[]
  modules: { name: string; created: number; pending: number; abnormal: number }[]
}

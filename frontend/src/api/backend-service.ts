import { request } from './client'
import { moduleMeta } from '@/data/modules'
import type {
  ActionResult,
  EntryRow,
  OverviewResult,
  PageResult,
  ReceiptView,
} from '@/data/types'

export { moduleMeta }

/** 本次动作请求的入口信息：谁发的、带哪张回执、是否只是预告在途。 */
export type ActionOptions = {
  receipt?: string
  inFlight?: boolean
  site?: string
}

function actionQuery(options: ActionOptions = {}): string {
  const params = new URLSearchParams()
  if (options.receipt) params.set('receipt', options.receipt)
  if (options.inFlight) params.set('inFlight', '1')
  if (options.site) params.set('site', options.site)
  const query = params.toString()
  return query ? `?${query}` : ''
}

export async function listEntries(
  key: string,
  filters: Record<string, string> = {},
): Promise<PageResult> {
  const query = new URLSearchParams(filters).toString()
  const response = await request(`/api/${key}?${query}`)
  if (!response.ok) throw new Error('业务数据读取失败')
  return await response.json()
}

export async function getEntry(key: string, id: number): Promise<EntryRow> {
  const response = await request(`/api/${key}/${id}`)
  if (!response.ok) throw new Error('业务记录读取失败')
  return await response.json()
}

export async function createEntry(
  key: string,
  values: Record<string, string>,
): Promise<ActionResult> {
  const response = await request(`/api/${key}`, {
    method: 'POST',
    body: JSON.stringify({ values }),
  })
  return await response.json()
}

export async function runAction(
  key: string,
  id: number,
  action: string,
  options: ActionOptions = {},
): Promise<ActionResult> {
  const response = await request(`/api/${key}/${id}/actions${actionQuery(options)}`, {
    method: 'POST',
    body: JSON.stringify({ action, ...options }),
  })
  return await response.json()
}

/** 登记一张尚在途中的分发回执（原入口在发请求前调用）。 */
export async function beginReceipt(
  meetingId: number,
  receipt?: string,
): Promise<ActionResult> {
  const response = await request('/api/receipts', {
    method: 'POST',
    body: JSON.stringify({ meetingId, receipt }),
  })
  return await response.json()
}

/** 按回执号（M-56）或纪要编号查当前处理状态。 */
export async function loadReceipt(receipt: string): Promise<ReceiptView> {
  const response = await request(`/api/receipts/${encodeURIComponent(receipt)}`)
  if (!response.ok) throw new Error(`回执 ${receipt} 尚未登记`)
  return await response.json()
}

export async function loadMeetingReceipt(meetingId: number): Promise<ReceiptView> {
  const response = await request(`/api/meetings/${meetingId}/receipt`)
  if (!response.ok) throw new Error(`会议纪要 ${meetingId} 暂无分发回执`)
  return await response.json()
}

export async function downloadEntries(
  key: string,
  filters: Record<string, string> = {},
): Promise<void> {
  const query = new URLSearchParams(filters).toString()
  const response = await request(`/api/${key}/export?${query}`)
  if (!response.ok) throw new Error('业务数据导出失败')
  const url = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${key}.csv`
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

export async function loadOverview(): Promise<OverviewResult> {
  const response = await request('/api/overview')
  if (!response.ok) throw new Error('运营概览读取失败')
  return await response.json()
}

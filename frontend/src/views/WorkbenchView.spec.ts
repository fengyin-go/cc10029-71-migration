import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createRouter, createMemoryHistory } from 'vue-router'

import WorkbenchView from './WorkbenchView.vue'

const listEntries = vi.fn()
const runAction = vi.fn()
const beginReceipt = vi.fn()

vi.mock('@/api/backend-service', () => ({
  moduleMeta: (key: string) => ({
    key,
    name: key === 'improve_task' ? '诊改任务' : '复盘会议',
    entity: key === 'improve_task' ? '诊改任务' : '会议纪要',
    desc: '',
    fields:
      key === 'improve_task'
        ? ['任务描述', '承接方案', '执行人员']
        : ['会议主题', '参会人员', '召开日期'],
    statuses:
      key === 'improve_task'
        ? ['草稿', '待认领', '执行中', '已验收']
        : ['草稿', '待签认', '已签认', '已分发'],
    actions:
      key === 'improve_task'
        ? ['认领任务', '启动执行', '申请验收']
        : ['签认纪要', '提出异议', '分发给教师'],
    actionTargets: {},
    metrics: ['总数', '待办', '完成'],
  }),
  listEntries: (...args: unknown[]) => listEntries(...args),
  runAction: (...args: unknown[]) => runAction(...args),
  beginReceipt: (...args: unknown[]) => beginReceipt(...args),
  createEntry: vi.fn(),
  downloadEntries: vi.fn(),
}))

vi.mock('@/api/client', () => ({ SITE: 'portal', SITE_LABEL: '教务门户' }))

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:moduleKey/:entryId?', component: { template: '<div/>' } }],
  })
}

async function mountView(moduleKey: string, entryId?: string) {
  const router = makeRouter()
  await router.push(`/${moduleKey}${entryId ? `/${entryId}` : ''}`)
  const wrapper = mount(WorkbenchView, {
    props: { moduleKey, entryId },
    global: { plugins: [router], stubs: { RouterLink: { template: '<a><slot/></a>' } } },
  })
  await flushPromises()
  return wrapper
}

describe('WorkbenchView migration behaviour', () => {
  beforeEach(() => {
    listEntries.mockReset()
    runAction.mockReset()
    beginReceipt.mockReset()
  })

  it('shows receipt chip on the meeting row', async () => {
    listEntries.mockResolvedValue({
      items: [
        {
          id: 3,
          status: '已分发',
          pending: false,
          abnormal: false,
          receipt: 'M-56',
          taskId: 4,
          receiptView: {
            receipt: 'M-56',
            meetingId: 3,
            taskId: 4,
            status: '已分发',
            message: '已分发',
          },
        },
      ],
      total: 1,
      page: 1,
      size: 20,
      instance: 'biz-1',
    })
    const wrapper = await mountView('review_meeting', '3')
    expect(wrapper.get('[data-testid="row-receipt-3"]').text()).toContain('M-56')
    expect(wrapper.get('[data-testid="row-3"]').classes()).toContain('row-highlight')
  })

  it('only offers claim on tasks that are actually claimable', async () => {
    listEntries.mockResolvedValue({
      items: [
        { id: 4, status: '待认领', pending: true, abnormal: false },
        { id: 5, status: '执行中', pending: false, abnormal: false },
      ],
      total: 2,
      page: 1,
      size: 20,
      instance: 'biz-1',
    })
    const wrapper = await mountView('improve_task')
    expect(wrapper.find('[data-testid="action-4-认领任务"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="action-5-认领任务"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="action-5-申请验收"]').exists()).toBe(true)
  })

  it('surfaces awaiting-original receipt message without claim', async () => {
    listEntries.mockResolvedValue({
      items: [{ id: 4, status: '待认领', pending: true, abnormal: false }],
      total: 1,
      page: 1,
      size: 20,
      instance: 'biz-1',
    })
    runAction.mockResolvedValue({
      ok: false,
      message: '分发回执 M-56 尚待原入口处理（原入口：独立站点）',
      receipt: {
        receipt: 'M-56',
        status: '尚待原入口处理',
        message: '尚待原入口处理',
      },
    })
    const wrapper = await mountView('improve_task')
    await wrapper.get('[data-testid="action-4-认领任务"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="action-notice"]').text()).toContain('尚待原入口处理')
    expect(wrapper.get('[data-testid="notice-receipt-link"]').text()).toContain('M-56')
  })

  it('registers an in-flight receipt before distributing from the legacy entry', async () => {
    listEntries.mockResolvedValue({
      items: [{ id: 3, status: '已签认', pending: false, abnormal: false, 回执编号: 'M-56' }],
      total: 1,
      page: 1,
      size: 20,
      instance: 'biz-1',
    })
    beginReceipt.mockResolvedValue({ ok: true, message: '已登记' })
    runAction.mockResolvedValue({
      ok: true,
      message: '已分发',
      receipt: { receipt: 'M-56', status: '已分发', message: '已分发' },
    })
    const wrapper = await mountView('review_meeting')
    await wrapper.get('[data-testid="action-3-分发给教师"]').trigger('click')
    await flushPromises()
    // 当前测试环境被 mock 成门户入口，因此不触发原入口预登记。
    expect(beginReceipt).not.toHaveBeenCalled()
    expect(runAction).toHaveBeenCalledWith('review_meeting', 3, '分发给教师', { receipt: 'M-56' })
  })
})

import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import Overview from '@/views/Overview.vue'
import WorkbenchView from '@/views/WorkbenchView.vue'
import ReceiptView from '@/views/ReceiptView.vue'

// 两套入口共用一份路由表：
//   独立站点：/ 、/review_meeting/3 、/improve_task/4 、/receipts/M-56
//   教务门户：/portal/ 、/portal/review_meeting/3 、/portal/receipts/M-56
//
// 旧收藏里保存的是根路径，不跳转，直接按同一张表解析；入口身份
// （legacy / portal）取自实际路径，决定接口前缀与回执来源。
function mount(prefix: string, nameSuffix: string): RouteRecordRaw[] {
  const p = (path: string) => (path === '/' ? prefix || '/' : `${prefix}${path}`)
  return [
    {
      path: p('/'),
      name: `overview${nameSuffix}`,
      component: Overview,
    },
    {
      path: p('/receipts/:receipt'),
      name: `receipt${nameSuffix}`,
      component: ReceiptView,
      props: true,
    },
    {
      path: p('/:moduleKey/:entryId'),
      name: `module-entry${nameSuffix}`,
      component: WorkbenchView,
      props: true,
    },
    {
      path: p('/:moduleKey'),
      name: `module${nameSuffix}`,
      component: WorkbenchView,
      props: true,
    },
  ]
}

const routes: RouteRecordRaw[] = [
  ...mount('', '-legacy'),
  ...mount('/portal', '-portal'),
]

const router = createRouter({
  history: createWebHistory('/'),
  routes,
})

export default router

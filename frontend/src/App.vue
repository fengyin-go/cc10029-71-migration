<template>
  <div class="app-shell">
    <aside class="app-side">
      <h1 class="app-title">教学诊改协同台</h1>
      <p class="app-site" data-testid="entry-site">
        <span class="site-badge" :class="SITE === 'portal' ? 'site-portal' : 'site-legacy'">{{ SITE_LABEL }}</span>
        <span class="site-path" data-testid="entry-path">{{ entryPath }}</span>
      </p>
      <a
        class="entry-switch"
        :href="switchEntryLink(entryPath)"
        data-testid="entry-switch"
        @click.prevent="switchEntry"
      >
        {{ SITE === 'portal' ? '返回独立站点' : '进入教务门户' }}
      </a>
      <nav class="nav-list">
        <RouterLink v-for="item in navItems" :key="item.path" :to="item.path" class="nav-item">
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>
    <main class="app-main">
      <header class="app-head">
        <span class="head-desc">教师、教研室主任和教务处在课堂观摩后填写教学反馈、制定改进方案、跟踪实施进度并在学期末完成复盘归档。</span>
        <span class="head-user">当前值班：应用开发组</span>
      </header>
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import { SITE, SITE_LABEL } from '@/api/client'
import { switchEntryLink } from '@/api/entry'
import { MODULES } from '@/data/modules'

const route = useRoute()
const entryPath = computed(() => route.fullPath)

/**
 * 切换入口必须整页加载：入口身份（接口前缀、回执来源）在页面初始化时确定，
 * 单页内跳转会让旧入口的请求继续打到门户前缀。
 */
function switchEntry() {
  window.location.assign(switchEntryLink(entryPath.value))
}

const navItems = [
  { label: '运营概览', path: '/' },
  ...MODULES.map((meta) => ({ label: meta.name, path: `/${meta.key}` })),
].map((item) => ({
  ...item,
  // 门户入口的导航链接都带上 /portal 前缀，切换页面时入口身份保持不变。
  path: SITE === 'portal'
    ? (item.path === '/' ? '/portal' : `/portal${item.path}`)
    : item.path,
}))
</script>

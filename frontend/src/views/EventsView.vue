<template>
  <div class="page-stack">
    <header class="page-head">
      <div>
        <h1>事件日历</h1>
        <p>把宏观数据、EIA / USDA、月末换月和手动导入事件放在一起看。</p>
      </div>
      <div class="head-actions">
        <button class="secondary light" :disabled="loading" @click="loadCalendar()">{{ loading ? '刷新中...' : '刷新' }}</button>
      </div>
    </header>

    <div v-if="error" class="notice error">{{ error }}</div>
    <div v-else-if="calendar.summary" class="notice success">
      共 {{ calendar.summary.count }} 个事件，{{ calendar.summary.high_count }} 个高优先级事件。
      <span v-if="calendar.summary.next_event">下一个事件：{{ calendar.summary.next_event.date }} · {{ calendar.summary.next_event.title }}</span>
    </div>

    <section class="summary-grid">
      <article class="summary-card">
        <div class="summary-label">统计窗口</div>
        <div class="summary-value">{{ calendar.window_days || 14 }} 天</div>
        <div class="summary-sub">起始日：{{ calendar.trade_date || '-' }}</div>
      </article>
      <article class="summary-card">
        <div class="summary-label">事件总数</div>
        <div class="summary-value">{{ calendar.summary?.count ?? 0 }}</div>
        <div class="summary-sub">包含规则事件 + 手动导入事件</div>
      </article>
      <article class="summary-card">
        <div class="summary-label">高优先级</div>
        <div class="summary-value">{{ calendar.summary?.high_count ?? 0 }}</div>
        <div class="summary-sub">宏观 / USDA / 月末窗口优先显示</div>
      </article>
    </section>

    <section class="calendar-list">
      <article v-for="item in calendar.items || []" :key="`${item.date}-${item.title}`" class="calendar-item" :class="`importance-${item.importance || 'normal'}`">
        <div class="calendar-top">
          <div>
            <b>{{ item.title }}</b>
            <span>{{ item.category }} · {{ item.source }}</span>
          </div>
          <em>{{ item.date }}</em>
        </div>
        <p>{{ item.summary }}</p>
        <div v-if="item.impact" class="calendar-impact">影响：{{ item.impact }}</div>
        <div v-if="item.note" class="calendar-note">备注：{{ item.note }}</div>
      </article>
      <div v-if="!loading && !(calendar.items || []).length" class="empty-state large">暂无事件。可以在 <code>config/event_calendar.json</code> 里手动导入。</div>
    </section>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import api from '../api.js'

const loading = ref(false)
const error = ref('')
const calendar = reactive({ items: [], summary: null, trade_date: '', window_days: 14 })

async function loadCalendar() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/events/calendar', { params: { window_days: 21 } })
    calendar.items = data?.items || []
    calendar.summary = data?.summary || null
    calendar.trade_date = data?.trade_date || ''
    calendar.window_days = data?.window_days || 14
  } catch (err) {
    error.value = err?.response?.data?.detail || err?.message || '加载事件日历失败'
  } finally {
    loading.value = false
  }
}

onMounted(loadCalendar)
</script>

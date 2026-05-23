<template>
  <div class="history">
    <h2 class="page-title">历史复盘</h2>
    <SectionCard title="已生成的日报">
      <div v-if="loading" class="empty-state">正在加载历史日报...</div>
      <div v-else-if="!reports.length" class="empty-state">还没有历史日报，先去「今日看板」生成一份。</div>
      <div v-else class="date-list">
        <router-link
          v-for="item in reports"
          :key="item.trade_date"
          class="date-item"
          :to="`/?date=${item.trade_date}`"
        >
          <div>
            <div class="date">{{ formatDate(item.trade_date) }}</div>
            <div class="generated">{{ formatDateTime(item.generated_at) }}</div>
          </div>
          <span class="score">{{ item.score ?? '-' }} 分</span>
          <span class="status" :class="statusClass(item.status)">{{ statusText(item.status) }}</span>
          <span class="summary">{{ item.summary || '暂无摘要' }}</span>
        </router-link>
      </div>
    </SectionCard>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import api from '../api.js'
import SectionCard from '../components/SectionCard.vue'

const reports = ref([])
const loading = ref(false)

function formatDate(value) {
  if (!value) return '-'
  const text = String(value)
  if (/^\d{8}$/.test(text)) return `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6)}`
  return text
}

function formatDateTime(value) {
  if (!value) return '暂无生成时间'
  return String(value).replace('T', ' ').slice(0, 19)
}

function statusText(status) {
  return ({ generated: '已完成', draft: '未完成', failed: '失败' }[status]) || status || '未知'
}

function statusClass(status) {
  return status === 'generated' ? 'ok' : status === 'failed' ? 'bad' : 'neutral'
}

onMounted(async () => {
  loading.value = true
  try {
    const { data } = await api.get('/reports')
    reports.value = data || []
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.page-title { margin-bottom: 20px; color: #1a1a2e; }
.date-list { display: flex; flex-direction: column; gap: 10px; }
.date-item {
  display: grid;
  grid-template-columns: 150px 80px 78px 1fr;
  gap: 12px;
  align-items: center;
  padding: 14px 16px;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 10px;
  text-decoration: none;
  color: #333;
  transition: transform .15s ease, border-color .15s ease, box-shadow .15s ease;
}
.date-item:hover { transform: translateY(-1px); border-color: #e94560; box-shadow: 0 4px 14px rgba(233,69,96,.08); }
.date { font-weight: 700; color: #1a1a2e; }
.generated { margin-top: 3px; font-size: 12px; color: #999; }
.score { font-weight: 700; color: #e94560; }
.status { width: fit-content; border-radius: 999px; padding: 4px 9px; font-size: 12px; }
.status.ok { background: #e9fbf5; color: #0f9b73; }
.status.bad { background: #fff0f0; color: #c53b3b; }
.status.neutral { background: #f1f3f8; color: #666; }
.summary { color: #666; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.empty-state { padding: 28px; text-align: center; color: #888; background: #fafafa; border-radius: 10px; }
@media (max-width: 900px) {
  .date-item { grid-template-columns: 1fr; align-items: start; }
  .summary { white-space: normal; }
}
</style>

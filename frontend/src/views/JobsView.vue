<template>
  <div>
    <h2 class="page-title">任务记录</h2>
    <SectionCard title="最近任务">
      <SimpleTable :columns="columns" :data="rows" />
    </SectionCard>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import api from '../api.js'
import SectionCard from '../components/SectionCard.vue'
import SimpleTable from '../components/SimpleTable.vue'

const jobs = ref([])
const columns = ['ID', '任务', '状态', '交易日', '开始', '结束', '消息']
const rows = computed(() => jobs.value.map(j => [j.id, j.name, j.status, j.trade_date || '-', fmt(j.started_at), fmt(j.finished_at), j.message || '-']))
function fmt(v) { return v ? String(v).replace('T', ' ').slice(0, 19) : '-' }
onMounted(async () => { jobs.value = (await api.get('/jobs')).data })
</script>

<style scoped>
.page-title { margin-bottom: 20px; color: #1a1a2e; }
</style>

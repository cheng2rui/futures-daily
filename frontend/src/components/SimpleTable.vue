<template>
  <div class="simple-table">
    <table>
      <thead>
        <tr>
          <th v-for="col in columns" :key="col">{{ col }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, i) in data" :key="i">
          <td v-for="(val, j) in row" :key="j" :class="valueClass(val)">{{ val }}</td>
        </tr>
        <tr v-if="!data || data.length === 0">
          <td :colspan="columns.length" class="empty">暂无数据</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
defineProps({
  columns: { type: Array, default: () => [] },
  data: { type: Array, default: () => [] },
})
function valueClass(v) {
  const s = String(v ?? '')
  if (/^\+/.test(s)) return 'market-up'
  if (/^-/.test(s)) return 'market-down'
  if (/正常|成功|已解决/.test(s)) return 'status-positive'
  if (/缺失|失败|错误|待处理/.test(s)) return 'status-negative'
  return ''
}
</script>

<style scoped>
.simple-table { width:100%; overflow:auto; }
.simple-table table { width:100%; border-collapse:separate; border-spacing:0; font-size:13px; min-width:620px; }
.simple-table th { position:sticky; top:0; z-index:1; background:#f8fafc; padding:11px 12px; text-align:left; font-weight:900; color:#475569; border-bottom:1px solid #e2e8f0; white-space:nowrap; }
.simple-table td { padding:11px 12px; border-bottom:1px solid #f1f5f9; color:#1f2937; white-space:nowrap; }
.simple-table tbody tr:hover td { background:#fbfdff; }
.simple-table tr:last-child td { border-bottom:none; }
.simple-table .empty { text-align:center; color:#94a3b8; padding:28px; }
.market-up { color:#d93655 !important; font-weight:800; }
.market-down { color:#12966b !important; font-weight:800; }
.status-positive { color:#12966b !important; font-weight:800; }
.status-negative { color:#d93655 !important; font-weight:800; }
</style>

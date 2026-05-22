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
          <td v-for="(val, j) in row" :key="j">{{ val }}</td>
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
</script>

<style scoped>
.simple-table table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
.simple-table th {
  background: #fafafa;
  padding: 10px 12px;
  text-align: left;
  font-weight: 600;
  color: #555;
  border-bottom: 2px solid #eee;
}
.simple-table td {
  padding: 10px 12px;
  border-bottom: 1px solid #f5f5f5;
  color: #333;
}
.simple-table tr:last-child td { border-bottom: none; }
.simple-table .empty {
  text-align: center;
  color: #aaa;
  padding: 24px;
}
</style>

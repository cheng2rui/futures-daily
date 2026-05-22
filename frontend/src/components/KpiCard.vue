<template>
  <div class="kpi-card" :style="{ borderLeftColor: color }">
    <div class="kpi-label">{{ label }}</div>
    <div class="kpi-value">{{ value }}<span class="kpi-unit">{{ unit }}</span></div>
  </div>
</template>

<script setup>
defineProps({
  label: String,
  value: [String, Number],
  unit: { type: String, default: '' },
  color: { type: String, default: '#e94560' },
})
</script>

<style scoped>
.kpi-card {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  border-left: 4px solid;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.kpi-label {
  font-size: 13px;
  color: #888;
  margin-bottom: 8px;
}
.kpi-value {
  font-size: 28px;
  font-weight: 700;
  color: #1a1a2e;
}
.kpi-unit {
  font-size: 14px;
  font-weight: 400;
  color: #888;
  margin-left: 4px;
}
</style>

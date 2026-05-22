<template>
  <div class="app">
    <nav class="sidebar">
      <div class="logo">Futures Daily</div>
      <router-link to="/">今日</router-link>
      <router-link to="/history">历史</router-link>
      <router-link to="/seats">持仓席位</router-link>
      <router-link to="/dataset">数据资产</router-link>
      <router-link to="/jobs">任务</router-link>
      <router-link to="/settings">设置</router-link>
    </nav>
    <main class="content">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.app {
  display: flex;
  min-height: 100vh;
}
.sidebar {
  width: 200px;
  background: #1a1a2e;
  color: #fff;
  padding: 24px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.logo {
  font-size: 18px;
  font-weight: 700;
  margin-bottom: 24px;
  color: #e94560;
}
.sidebar a {
  color: #ccc;
  text-decoration: none;
  padding: 10px 12px;
  border-radius: 8px;
  transition: background 0.2s;
}
.sidebar a:hover,
.sidebar a.router-link-active {
  background: #e94560;
  color: #fff;
}
.content {
  flex: 1;
  background: #f5f5f5;
  padding: 24px;
  overflow-y: auto;
}
</style>

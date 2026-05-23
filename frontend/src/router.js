import { createRouter, createWebHistory } from 'vue-router'
import TodayView from './views/TodayView.vue'
import HistoryView from './views/HistoryView.vue'
import SymbolView from './views/SymbolView.vue'
import SeatsView from './views/SeatsView.vue'
import SettingsView from './views/SettingsView.vue'
import JobsView from './views/JobsView.vue'
import DatasetView from './views/DatasetView.vue'
import DataDiagnosticsView from './views/DataDiagnosticsView.vue'
import EventsView from './views/EventsView.vue'

const routes = [
  { path: '/', component: TodayView },
  { path: '/history', component: HistoryView },
  { path: '/symbol/:code', component: SymbolView },
  { path: '/seats', component: SeatsView },
  { path: '/dataset', component: DatasetView },
  { path: '/diagnostics', component: DataDiagnosticsView },
  { path: '/events', component: EventsView },
  { path: '/jobs', component: JobsView },
  { path: '/settings', component: SettingsView },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})

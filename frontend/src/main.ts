import {
  CaretRight,
  Collection,
  DataAnalysis,
  HomeFilled,
  Microphone,
  Notebook,
  Reading,
  Search,
  Setting,
  UploadFilled,
  UserFilled,
} from '@element-plus/icons-vue'
import { ElLoading, ElMessage, ElMessageBox } from 'element-plus'
import 'element-plus/es/components/loading/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import { createPinia } from 'pinia'
import { createApp } from 'vue'
import axios from 'axios'
import App from './App.vue'
import router from './router'
import './styles.css'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(ElLoading)

const icons = {
  CaretRight,
  Collection,
  DataAnalysis,
  HomeFilled,
  Microphone,
  Notebook,
  Reading,
  Search,
  Setting,
  UploadFilled,
  UserFilled,
}
for (const [name, component] of Object.entries(icons)) {
  app.component(name, component)
}

// ---------- 全局错误兜底 ----------
let lastNoticeAt = 0
function notify(message: string) {
  const now = Date.now()
  if (now - lastNoticeAt < 2000) return
  lastNoticeAt = now
  ElMessage.error(message)
}

app.config.errorHandler = (error) => {
  console.error('[app error]', error)
  notify('页面出现异常，请刷新后重试')
}

window.addEventListener('unhandledrejection', (event) => {
  // Axios 错误已由拦截器统一提示，避免重复弹窗
  if (axios.isAxiosError(event.reason)) return
  console.error('[unhandled rejection]', event.reason)
  notify('请求或页面处理失败，请稍后重试')
})

router.onError((error) => {
  console.error('[router error]', error)
  const message = String(error)
  if (/dynamically imported module|Importing a module script failed/i.test(message)) {
    ElMessageBox.confirm('页面资源已更新，请刷新后继续使用。', '需要刷新', {
      confirmButtonText: '刷新页面',
      cancelButtonText: '稍后',
      type: 'warning',
    })
      .then(() => window.location.reload())
      .catch(() => undefined)
    return
  }
  notify('页面加载失败，请刷新后重试')
})

app.mount('#app')

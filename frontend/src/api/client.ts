import { ElMessage } from 'element-plus'
import axios from 'axios'

declare module 'axios' {
  export interface AxiosRequestConfig {
    /** 不弹出全局错误提示（例如未登录时探测 /auth/me） */
    silent?: boolean
  }
}

const client = axios.create({ baseURL: '/api', timeout: 30000 })

// 这些接口的 401 属于预期结果（未登录 / 密码错误），不触发全局跳转
const AUTH_ENDPOINTS = ['/auth/login', '/auth/register', '/auth/me']

function errMsg(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const status = err.response?.status
    const detail = err.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail.length) {
      const first = detail[0]
      if (first?.msg) return `参数错误：${first.msg}`
    }
    if (status === 413) return '文件过大，请缩小后重试'
    if (status === 429) return '操作过于频繁，请稍后再试'
    if (status === 503) return '数据库暂不可用，请稍后重试'
    if (err.code === 'ECONNABORTED') return '请求超时，请重试'
    if (!err.response && typeof navigator !== 'undefined' && !navigator.onLine) {
      return '网络已断开，请检查连接后重试'
    }
    return err.message || '请求失败'
  }
  return '请求失败'
}

client.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const url = (err.config?.url as string | undefined) ?? ''
    const isAuthEndpoint = AUTH_ENDPOINTS.some((path) => url.startsWith(path))

    if (err.response?.status === 401 && !isAuthEndpoint) {
      // 会话过期：由 App.vue 统一清空登录态并跳转登录页
      window.dispatchEvent(new Event('auth:unauthorized'))
    }
    if (!err.config?.silent) {
      ElMessage.error(errMsg(err))
    }
    return Promise.reject(err)
  },
)

export default client

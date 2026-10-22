import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  deleteAccount as apiDeleteAccount,
  getMe,
  login as apiLogin,
  logout as apiLogout,
  register as apiRegister,
} from '@/api'
import type { AuthUser } from '@/api/types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<AuthUser | null>(null)
  const loaded = ref(false)

  /** 应用启动/路由跳转前调用；401 视为未登录，不弹错误。 */
  async function ensureLoaded() {
    if (loaded.value) return
    try {
      user.value = await getMe()
    } catch {
      user.value = null
    } finally {
      loaded.value = true
    }
  }

  async function login(username: string, password: string) {
    user.value = await apiLogin({ username, password })
    loaded.value = true
  }

  async function register(username: string, password: string) {
    user.value = await apiRegister({ username, password })
    loaded.value = true
  }

  async function logout() {
    try {
      await apiLogout()
    } finally {
      user.value = null
      loaded.value = true
    }
  }

  async function deleteAccount(password: string) {
    await apiDeleteAccount(password)
    user.value = null
    loaded.value = true
  }

  function clear() {
    user.value = null
    loaded.value = true
  }

  return {
    user,
    loaded,
    ensureLoaded,
    login,
    register,
    logout,
    deleteAccount,
    clear,
  }
})

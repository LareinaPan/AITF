import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  fetchCurrentUser,
  login as loginApi,
  register as registerApi,
  type LoginPayload,
  type RegisterPayload,
  type User,
} from '@/api/auth'
import { clearStoredToken, getStoredToken, setStoredToken } from '@/utils/auth-storage'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(getStoredToken())
  const user = ref<User | null>(null)
  const initialized = ref(false)

  const isAuthenticated = computed(() => Boolean(token.value))

  function setSession(accessToken: string, currentUser: User): void {
    token.value = accessToken
    user.value = currentUser
    setStoredToken(accessToken)
  }

  function clearSession(): void {
    token.value = null
    user.value = null
    clearStoredToken()
  }

  async function initialize(): Promise<void> {
    if (initialized.value) {
      return
    }

    if (!token.value) {
      initialized.value = true
      return
    }

    try {
      user.value = await fetchCurrentUser()
    } catch {
      clearSession()
    } finally {
      initialized.value = true
    }
  }

  async function login(payload: LoginPayload): Promise<void> {
    const data = await loginApi(payload)
    setSession(data.access_token, data.user)
  }

  async function register(payload: RegisterPayload): Promise<void> {
    await registerApi(payload)
    await login(payload)
  }

  async function logout(): Promise<void> {
    clearSession()
  }

  return {
    token,
    user,
    initialized,
    isAuthenticated,
    initialize,
    login,
    register,
    logout,
    clearSession,
  }
})

import { reactive, computed } from 'vue'
import { get, post } from '@shared/api/httpClient'

const TOKEN_KEY = 'velpos_auth_token'
const USER_KEY = 'velpos_auth_user'

const state = reactive({
  token: localStorage.getItem(TOKEN_KEY) || null,
  user: JSON.parse(localStorage.getItem(USER_KEY) || 'null'),
  mode: null,
  autoLogin: false,
  initialized: false,
})

export const isAuthenticated = computed(() => !!state.token || state.mode === 'dev')
export const currentUser = computed(() => state.user)
export const isAdmin = computed(() => state.user?.role === 'admin')
export const appMode = computed(() => state.mode)
export const authInitialized = computed(() => state.initialized)

export function getToken() {
  return state.token
}

export async function initAuth() {
  const config = await get('/auth/config')
  state.mode = config.mode
  state.autoLogin = config.auto_login

  if (state.mode === 'dev') {
    state.user = { id: 1, username: 'admin', display_name: 'Admin', role: 'admin' }
    state.token = null
    state.initialized = true
    return true
  }

  if (state.token) {
    try {
      const user = await get('/auth/me')
      state.user = user
      state.initialized = true
      return true
    } catch (error) {
      if (error?.status !== 401) {
        throw error
      }
      clearAuth()
    }
  }

  state.initialized = true
  return false
}

export async function login(username, password) {
  const data = await post('/auth/login', { username, password })
  state.token = data.token
  state.user = data.user
  localStorage.setItem(TOKEN_KEY, data.token)
  localStorage.setItem(USER_KEY, JSON.stringify(data.user))
  return data.user
}

export async function register(username, password, displayName) {
  return await post('/auth/register', {
    username,
    password,
    display_name: displayName || undefined,
  })
}

export function logout() {
  clearAuth()
}

function clearAuth() {
  state.token = null
  state.user = null
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

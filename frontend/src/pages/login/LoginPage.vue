<script setup>
import { ref } from 'vue'
import { login, register } from '@shared/lib/authStore'

const emit = defineEmits(['authenticated'])

const mode = ref('login')
const username = ref('')
const password = ref('')
const displayName = ref('')
const error = ref('')
const loading = ref(false)

async function handleSubmit() {
  error.value = ''
  loading.value = true
  try {
    if (mode.value === 'login') {
      await login(username.value, password.value)
    } else {
      await register(username.value, password.value, displayName.value)
      await login(username.value, password.value)
    }
    emit('authenticated')
  } catch (e) {
    error.value = e.message || 'Authentication failed'
  } finally {
    loading.value = false
  }
}

function toggleMode() {
  mode.value = mode.value === 'login' ? 'register' : 'login'
  error.value = ''
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-header">
        <h1 class="login-title">Velpos</h1>
        <p class="login-subtitle">{{ mode === 'login' ? 'Sign in to your account' : 'Create a new account' }}</p>
      </div>

      <form class="login-form" @submit.prevent="handleSubmit">
        <div class="form-field">
          <label for="username">Username</label>
          <input
            id="username"
            v-model="username"
            type="text"
            autocomplete="username"
            required
            :disabled="loading"
          />
        </div>

        <div v-if="mode === 'register'" class="form-field">
          <label for="displayName">Display Name</label>
          <input
            id="displayName"
            v-model="displayName"
            type="text"
            :disabled="loading"
          />
        </div>

        <div class="form-field">
          <label for="password">Password</label>
          <input
            id="password"
            v-model="password"
            type="password"
            autocomplete="current-password"
            required
            :disabled="loading"
          />
        </div>

        <div v-if="error" class="form-error">{{ error }}</div>

        <button type="submit" class="submit-btn" :disabled="loading">
          {{ loading ? 'Loading...' : (mode === 'login' ? 'Sign In' : 'Register') }}
        </button>
      </form>

      <div class="login-footer">
        <button class="toggle-btn" @click="toggleMode">
          {{ mode === 'login' ? "Don't have an account? Register" : 'Already have an account? Sign In' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--layer-base);
}

.login-card {
  width: 100%;
  max-width: 380px;
  padding: 40px 32px;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-xl, 16px);
  box-shadow: var(--shadow-lg);
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
}

.login-header {
  text-align: center;
  margin-bottom: 32px;
}

.login-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 8px;
}

.login-subtitle {
  font-size: 14px;
  color: var(--text-muted);
  margin: 0;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-field label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.form-field input {
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md, 8px);
  background: var(--layer-base);
  color: var(--text-primary);
  font-size: 14px;
  transition: border-color 0.15s;
}

.form-field input:focus {
  outline: none;
  border-color: var(--accent);
}

.form-error {
  font-size: 13px;
  color: var(--red, #e53e3e);
  padding: 8px 12px;
  background: var(--red-dim, rgba(229, 62, 62, 0.1));
  border-radius: var(--radius-md, 8px);
}

.submit-btn {
  padding: 10px 16px;
  background: var(--accent);
  color: white;
  border: none;
  border-radius: var(--radius-md, 8px);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.15s;
}

.submit-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.login-footer {
  margin-top: 24px;
  text-align: center;
}

.toggle-btn {
  background: none;
  border: none;
  color: var(--accent);
  font-size: 13px;
  cursor: pointer;
}

.toggle-btn:hover {
  text-decoration: underline;
}
</style>

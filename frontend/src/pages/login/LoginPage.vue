<script setup>
import { computed, ref } from 'vue'
import { login, register } from '@shared/lib/authStore'

const emit = defineEmits(['authenticated'])

const mode = ref('login')
const username = ref('')
const password = ref('')
const displayName = ref('')
const error = ref('')
const loading = ref(false)
const showPassword = ref(false)

const isLogin = computed(() => mode.value === 'login')
const passwordAutocomplete = computed(() => isLogin.value ? 'current-password' : 'new-password')

async function handleSubmit() {
  error.value = ''
  loading.value = true
  try {
    if (isLogin.value) {
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
  mode.value = isLogin.value ? 'register' : 'login'
  error.value = ''
  showPassword.value = false
}
</script>

<template>
  <main class="login-page">
    <div class="ambient ambient-one" aria-hidden="true"></div>
    <div class="ambient ambient-two" aria-hidden="true"></div>
    <div class="grid-pattern" aria-hidden="true"></div>

    <section class="login-card" aria-labelledby="login-title">
      <header class="login-header">
        <div class="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M8.25 7.25 3.5 12l4.75 4.75M15.75 7.25 20.5 12l-4.75 4.75" />
            <path d="m13.8 5.5-3.6 13" />
          </svg>
        </div>
        <div class="product-name">Velpos</div>
        <p class="product-kicker">CODEX CONTROL PLANE</p>
        <h1 id="login-title" class="login-title">
          {{ isLogin ? 'Welcome back' : 'Create your account' }}
        </h1>
        <p class="login-subtitle">
          {{ isLogin ? 'Sign in to continue to your workspace.' : 'Set up your workspace access in a few seconds.' }}
        </p>
      </header>

      <form class="login-form" @submit.prevent="handleSubmit">
        <div v-if="!isLogin" class="form-field">
          <label for="displayName">Display name</label>
          <div class="input-shell">
            <svg class="field-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M20 21a8 8 0 0 0-16 0M12 13a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z" />
            </svg>
            <input
              id="displayName"
              v-model="displayName"
              type="text"
              autocomplete="name"
              placeholder="How should we call you?"
              :disabled="loading"
            />
          </div>
        </div>

        <div class="form-field">
          <label for="username">Username</label>
          <div class="input-shell">
            <svg class="field-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <circle cx="12" cy="8" r="4" />
              <path d="M4.5 21a7.5 7.5 0 0 1 15 0" />
            </svg>
            <input
              id="username"
              v-model="username"
              type="text"
              autocomplete="username"
              placeholder="Enter your username"
              required
              autofocus
              :disabled="loading"
            />
          </div>
        </div>

        <div class="form-field">
          <label for="password">Password</label>
          <div class="input-shell">
            <svg class="field-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <rect x="4" y="10" width="16" height="11" rx="3" />
              <path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3" />
            </svg>
            <input
              id="password"
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              :autocomplete="passwordAutocomplete"
              placeholder="Enter your password"
              required
              :disabled="loading"
            />
            <button
              class="password-toggle"
              type="button"
              :aria-label="showPassword ? 'Hide password' : 'Show password'"
              :aria-pressed="showPassword"
              :disabled="loading"
              @click="showPassword = !showPassword"
            >
              <svg v-if="showPassword" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="m3 3 18 18M10.6 10.7a2 2 0 0 0 2.7 2.7M9.9 4.2A10.8 10.8 0 0 1 12 4c5.5 0 9 5.5 9 5.5a15 15 0 0 1-2.1 2.7M6.2 6.2C4.2 7.5 3 9.5 3 9.5S6.5 15 12 15c1 0 2-.2 2.8-.5" />
              </svg>
              <svg v-else viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M3 12s3.5-5.5 9-5.5 9 5.5 9 5.5-3.5 5.5-9 5.5S3 12 3 12Z" />
                <circle cx="12" cy="12" r="2.5" />
              </svg>
            </button>
          </div>
        </div>

        <div v-if="error" class="form-error" role="alert" aria-live="polite">
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle cx="12" cy="12" r="9" />
            <path d="M12 7.5v5M12 16.5h.01" />
          </svg>
          <span>{{ error }}</span>
        </div>

        <button type="submit" class="submit-btn" :disabled="loading">
          <span v-if="loading" class="spinner" aria-hidden="true"></span>
          <span>{{ loading ? 'Please wait…' : (isLogin ? 'Sign in' : 'Create account') }}</span>
          <svg v-if="!loading" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M5 12h14M14 7l5 5-5 5" />
          </svg>
        </button>
      </form>

      <footer class="login-footer">
        <span>{{ isLogin ? 'New to Velpos?' : 'Already have an account?' }}</span>
        <button type="button" class="toggle-btn" :disabled="loading" @click="toggleMode">
          {{ isLogin ? 'Create an account' : 'Sign in instead' }}
        </button>
      </footer>
    </section>

    <p class="page-note">
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M7 10V7a5 5 0 0 1 10 0v3M6 10h12a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2Z" />
      </svg>
      Secure workspace access
    </p>
  </main>
</template>

<style scoped>
.login-page {
  position: relative;
  isolation: isolate;
  min-height: 100vh;
  min-height: 100svh;
  overflow: auto;
  display: grid;
  place-items: center;
  padding: 48px 24px 76px;
  background:
    radial-gradient(circle at 50% 0%, color-mix(in srgb, var(--accent) 11%, transparent), transparent 38%),
    linear-gradient(180deg, color-mix(in srgb, var(--layer-base) 96%, var(--accent) 4%), var(--layer-base));
}

.grid-pattern {
  position: fixed;
  inset: 0;
  z-index: -2;
  opacity: 0.28;
  background-image:
    linear-gradient(var(--border-subtle) 1px, transparent 1px),
    linear-gradient(90deg, var(--border-subtle) 1px, transparent 1px);
  background-size: 44px 44px;
  mask-image: linear-gradient(to bottom, black, transparent 78%);
  pointer-events: none;
}

.ambient {
  position: fixed;
  z-index: -1;
  width: 360px;
  height: 360px;
  border-radius: 50%;
  filter: blur(100px);
  opacity: 0.12;
  pointer-events: none;
}

.ambient-one {
  top: -180px;
  left: calc(50% - 360px);
  background: var(--accent);
}

.ambient-two {
  right: calc(50% - 400px);
  bottom: -240px;
  background: var(--purple);
}

.login-card {
  width: min(100%, 428px);
  padding: 34px 38px 30px;
  border: 1px solid color-mix(in srgb, var(--glass-border) 82%, var(--text-primary) 18%);
  border-radius: 22px;
  background: color-mix(in srgb, var(--glass-bg-strong) 94%, transparent);
  box-shadow:
    0 28px 80px rgba(0, 0, 0, 0.26),
    0 2px 10px rgba(0, 0, 0, 0.12),
    inset 0 1px 0 var(--glass-highlight);
  backdrop-filter: blur(22px) saturate(125%);
}

.login-header {
  text-align: center;
  margin-bottom: 28px;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 50px;
  height: 50px;
  margin: 0 auto 12px;
  border: 1px solid color-mix(in srgb, var(--accent) 34%, var(--border));
  border-radius: 15px;
  background: linear-gradient(145deg, color-mix(in srgb, var(--accent) 21%, var(--bg-tertiary)), var(--bg-secondary));
  color: var(--accent-hover);
  box-shadow: 0 10px 26px var(--accent-dim), inset 0 1px 0 rgba(255, 255, 255, 0.1);
}

.brand-mark svg {
  width: 27px;
  height: 27px;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.product-name {
  color: var(--text-primary);
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.product-kicker {
  margin: 2px 0 22px;
  color: var(--text-muted);
  font: 600 10px/1.4 var(--font-mono);
  letter-spacing: 0.16em;
}

.login-title {
  margin: 0;
  color: var(--text-primary);
  font-size: clamp(26px, 4vw, 30px);
  font-weight: 650;
  line-height: 1.2;
  letter-spacing: -0.035em;
}

.login-subtitle {
  margin: 8px 0 0;
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.55;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 17px;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.form-field label {
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.015em;
}

.input-shell {
  position: relative;
  display: flex;
  align-items: center;
}

.field-icon {
  position: absolute;
  left: 14px;
  width: 18px;
  height: 18px;
  color: var(--text-muted);
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
  pointer-events: none;
  transition: color var(--transition-fast);
}

.input-shell input {
  width: 100%;
  height: 48px;
  padding: 0 44px 0 43px;
  border: 1px solid color-mix(in srgb, var(--border) 88%, var(--text-primary) 12%);
  border-radius: 11px;
  outline: none;
  background: color-mix(in srgb, var(--bg-input) 88%, transparent);
  color: var(--text-primary);
  font: 400 14px/1 var(--font-sans);
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast), background var(--transition-fast);
}

.input-shell input::placeholder {
  color: color-mix(in srgb, var(--text-muted) 78%, transparent);
}

.input-shell:hover input:not(:disabled) {
  border-color: color-mix(in srgb, var(--border) 64%, var(--text-secondary) 36%);
}

.input-shell:focus-within input {
  border-color: var(--accent);
  background: var(--bg-input);
  box-shadow: var(--ring);
}

.input-shell:focus-within .field-icon {
  color: var(--accent);
}

.input-shell input:disabled {
  cursor: not-allowed;
  opacity: 0.62;
}

.password-toggle {
  position: absolute;
  right: 4px;
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border: 0;
  border-radius: 8px;
  outline: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: color var(--transition-fast), background var(--transition-fast);
}

.password-toggle:hover:not(:disabled) {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.password-toggle:focus-visible {
  box-shadow: var(--ring);
}

.password-toggle svg {
  width: 18px;
  height: 18px;
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.form-error {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 10px 12px;
  border: 1px solid color-mix(in srgb, var(--red) 30%, transparent);
  border-radius: 10px;
  background: var(--red-dim);
  color: var(--red);
  font-size: 12px;
  line-height: 1.45;
}

.form-error svg {
  flex: 0 0 auto;
  width: 17px;
  height: 17px;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.submit-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  min-height: 48px;
  margin-top: 3px;
  padding: 0 18px;
  border: 1px solid color-mix(in srgb, var(--accent) 80%, white 20%);
  border-radius: 11px;
  background: linear-gradient(180deg, var(--accent-hover), var(--accent));
  box-shadow: 0 10px 24px var(--accent-dim), inset 0 1px 0 rgba(255, 255, 255, 0.2);
  color: var(--text-on-accent);
  font: 600 14px/1 var(--font-sans);
  cursor: pointer;
  transition: transform var(--transition-fast), filter var(--transition-fast), box-shadow var(--transition-fast);
}

.submit-btn:hover:not(:disabled) {
  filter: brightness(1.05);
  box-shadow: 0 12px 30px var(--accent-glow), inset 0 1px 0 rgba(255, 255, 255, 0.24);
  transform: translateY(-1px);
}

.submit-btn:active:not(:disabled) {
  transform: translateY(0);
}

.submit-btn:focus-visible {
  outline: 2px solid var(--text-primary);
  outline-offset: 3px;
}

.submit-btn:disabled,
.toggle-btn:disabled,
.password-toggle:disabled {
  cursor: not-allowed;
  opacity: 0.58;
}

.submit-btn svg {
  width: 17px;
  height: 17px;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.spinner {
  width: 17px;
  height: 17px;
  border: 2px solid rgba(255, 255, 255, 0.42);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

.login-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  margin-top: 25px;
  padding-top: 22px;
  border-top: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 13px;
}

.toggle-btn {
  min-height: 44px;
  padding: 0 4px;
  border: 0;
  border-radius: 6px;
  outline: none;
  background: transparent;
  color: var(--accent-hover);
  font: 600 13px/1 var(--font-sans);
  cursor: pointer;
  transition: color var(--transition-fast), background var(--transition-fast);
}

.toggle-btn:hover:not(:disabled) {
  color: var(--accent);
  text-decoration: underline;
  text-underline-offset: 3px;
}

.toggle-btn:focus-visible {
  box-shadow: var(--ring);
}

.page-note {
  position: absolute;
  bottom: 24px;
  left: 50%;
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 0;
  color: var(--text-muted);
  font: 500 11px/1.4 var(--font-mono);
  letter-spacing: 0.04em;
  transform: translateX(-50%);
}

.page-note svg {
  width: 14px;
  height: 14px;
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 520px) {
  .login-page {
    align-items: start;
    padding: 24px 14px 66px;
  }

  .login-card {
    margin: auto 0;
    padding: 28px 22px 24px;
    border-radius: 18px;
  }

  .login-header {
    margin-bottom: 24px;
  }

  .product-kicker {
    margin-bottom: 18px;
  }

  .login-footer {
    flex-wrap: wrap;
    margin-top: 21px;
    padding-top: 18px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .spinner {
    animation-duration: 1.5s;
  }

  .submit-btn {
    transition: none;
  }
}
</style>

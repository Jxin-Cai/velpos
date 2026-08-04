<script setup>
import { computed, reactive, ref, onMounted } from 'vue'
import { currentUser } from '@shared/lib/authStore'
import { useTimeout } from '@shared/lib/useTimeout'
import { listUsers, updateUserRole, updateUserStatus } from '../api/adminUserApi'

const users = ref([])
const loading = ref(false)
const error = ref('')
const success = ref('')
const query = ref('')
const operatingIds = reactive(new Set())
const { set: setTimer } = useTimeout()
const filteredUsers = computed(() => {
  const keyword = query.value.trim().toLocaleLowerCase()
  if (!keyword) return users.value
  return users.value.filter(user => [user.username, user.display_name, user.role]
    .some(value => String(value || '').toLocaleLowerCase().includes(keyword)))
})

function showSuccess(message) {
  success.value = message
  setTimer(() => { success.value = '' }, 2200)
}

async function loadUsers() {
  loading.value = true
  error.value = ''
  try {
    users.value = await listUsers()
  } catch (loadError) {
    error.value = loadError.message || '加载用户失败'
  } finally {
    loading.value = false
  }
}

async function handleRoleChange(user, event) {
  const newRole = event.target.value
  error.value = ''
  operatingIds.add(user.id)
  try {
    await updateUserRole(user.id, newRole)
    user.role = newRole
    showSuccess(`已更新 ${user.username} 的角色`)
  } catch (updateError) {
    error.value = updateError.message || '更新角色失败'
    event.target.value = user.role
  } finally {
    operatingIds.delete(user.id)
  }
}

async function handleToggleStatus(user) {
  const newStatus = !user.is_active
  error.value = ''
  operatingIds.add(user.id)
  try {
    await updateUserStatus(user.id, newStatus)
    user.is_active = newStatus
    showSuccess(`已${newStatus ? '启用' : '禁用'} ${user.username}`)
  } catch (updateError) {
    error.value = updateError.message || '更新用户状态失败'
  } finally {
    operatingIds.delete(user.id)
  }
}

onMounted(loadUsers)
</script>

<template>
  <div class="user-management-tab">
    <div class="tab-header">
      <div><span class="eyebrow">ACCESS CONTROL</span><h2 class="tab-title">用户管理</h2><p>管理账户角色及登录状态。</p></div>
    </div>

    <div v-if="error" class="error-state">{{ error }}</div>
    <div v-if="success" class="success-state" role="status">{{ success }}</div>

    <div class="user-toolbar">
      <label class="user-search">
        <span class="sr-only">搜索用户</span>
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>
        <input v-model="query" type="search" placeholder="搜索用户名、显示名或角色" />
      </label>
      <span>{{ filteredUsers.length }} / {{ users.length }} 个用户</span>
    </div>

    <div v-if="loading" class="loading-state">加载中...</div>

    <div v-else-if="users.length === 0" class="empty-state">
      <p>暂无用户</p>
    </div>

    <div v-else-if="filteredUsers.length === 0" class="empty-state">没有匹配的用户</div>

    <div v-else class="table-scroll" tabindex="0" aria-label="用户列表，可横向滚动">
    <table class="user-table">
      <thead>
        <tr>
          <th>用户名</th>
          <th>显示名</th>
          <th>角色</th>
          <th>状态</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="user in filteredUsers" :key="user.id">
          <td><strong>{{ user.username }}</strong><span v-if="user.id === currentUser?.id" class="self-badge">当前账号</span></td>
          <td>{{ user.display_name || '-' }}</td>
          <td>
            <select
              :value="user.role"
              :disabled="operatingIds.has(user.id) || user.id === currentUser?.id"
              :aria-label="`设置 ${user.username} 的角色`"
              :title="user.id === currentUser?.id ? '不能修改当前管理员自己的角色' : ''"
              @change="handleRoleChange(user, $event)"
              class="role-select"
            >
              <option value="admin">管理员</option>
              <option value="member">成员</option>
            </select>
          </td>
          <td>
            <span class="status-badge" :class="{ active: user.is_active !== false }">
              {{ user.is_active !== false ? '正常' : '已禁用' }}
            </span>
          </td>
          <td>
            <button
              class="glass-btn sm"
              :class="{ danger: user.is_active !== false }"
              type="button"
              :disabled="operatingIds.has(user.id) || user.id === currentUser?.id"
              :title="user.id === currentUser?.id ? '不能禁用当前登录账号' : ''"
              @click="handleToggleStatus(user)"
            >
              {{ operatingIds.has(user.id) ? '处理中…' : user.is_active !== false ? '禁用' : '启用' }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>
    </div>
  </div>
</template>

<style scoped>
.user-management-tab {
  max-width: 1080px;
  margin: 0 auto;
}

.tab-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.tab-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 4px 0 7px;
}

.tab-header p { margin: 0; color: var(--text-muted); font-size: 13px; }
.eyebrow { color: var(--accent); font-size: 9px; font-weight: 700; letter-spacing: .14em; }
.error-state { margin-bottom: 14px; padding: 10px 12px; border-radius: var(--radius-md); background: var(--red-dim); color: var(--red); font-size: 12px; }
.success-state { margin-bottom: 14px; padding: 10px 12px; border-radius: var(--radius-md); background: var(--green-dim); color: var(--green); font-size: 12px; }
.user-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 14px; color: var(--text-muted); font-size: 11px; }
.user-search { display: flex; align-items: center; width: min(420px, 100%); gap: 8px; padding: 0 11px; border: 1px solid var(--border-subtle); border-radius: 8px; background: var(--layer-base); }
.user-search:focus-within { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-dim); }
.user-search svg { width: 16px; fill: none; stroke: var(--text-muted); stroke-width: 1.8; }.user-search input { width: 100%; padding: 9px 0; border: 0; outline: 0; background: transparent; color: var(--text-primary); font: inherit; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
.table-scroll { max-width: 100%; overflow-x: auto; border: 1px solid var(--border-subtle); border-radius: 10px; }.table-scroll:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

.loading-state,
.empty-state {
  color: var(--text-muted);
  font-size: 14px;
  padding: 40px 0;
  text-align: center;
}

.user-table {
  min-width: 720px;
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.user-table th {
  text-align: left;
  padding: 10px 12px;
  color: var(--text-muted);
  font-weight: 500;
  font-size: 12px;
  border-bottom: 1px solid var(--border-subtle);
}

.user-table td {
  padding: 10px 12px;
  color: var(--text-primary);
  border-bottom: 1px solid var(--border-subtle);
}

.user-table tr:hover td {
  background: var(--layer-active);
}
.user-table td strong { font-weight: 600; }.self-badge { margin-left: 7px; padding: 2px 5px; border-radius: 4px; background: var(--accent-dim); color: var(--accent); font-size: 9px; }

.role-select {
  padding: 4px 8px;
  background: var(--layer-base);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 12px;
  cursor: pointer;
}

.status-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: 11px;
  font-weight: 500;
  background: var(--red-dim, rgba(239, 68, 68, 0.1));
  color: var(--red, #ef4444);
}

.status-badge.active {
  background: var(--green-dim, rgba(34, 197, 94, 0.1));
  color: var(--green, #22c55e);
}
@media (max-width: 640px) { .user-toolbar { align-items: stretch; flex-direction: column; }.user-search { width: 100%; } }
</style>

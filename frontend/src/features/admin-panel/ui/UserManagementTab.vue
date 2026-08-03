<script setup>
import { ref, onMounted } from 'vue'
import { listUsers, updateUserRole, updateUserStatus } from '../api/adminUserApi'

const users = ref([])
const loading = ref(false)

async function loadUsers() {
  loading.value = true
  try {
    users.value = await listUsers()
  } finally {
    loading.value = false
  }
}

async function handleRoleChange(user, newRole) {
  await updateUserRole(user.id, newRole)
  user.role = newRole
}

async function handleToggleStatus(user) {
  const newStatus = !user.is_active
  await updateUserStatus(user.id, newStatus)
  user.is_active = newStatus
}

onMounted(loadUsers)
</script>

<template>
  <div class="user-management-tab">
    <div class="tab-header">
      <h2 class="tab-title">用户管理</h2>
    </div>

    <div v-if="loading" class="loading-state">加载中...</div>

    <div v-else-if="users.length === 0" class="empty-state">
      <p>暂无用户</p>
    </div>

    <table v-else class="user-table">
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
        <tr v-for="user in users" :key="user.id">
          <td>{{ user.username }}</td>
          <td>{{ user.display_name || '-' }}</td>
          <td>
            <select
              :value="user.role"
              @change="handleRoleChange(user, $event.target.value)"
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
              @click="handleToggleStatus(user)"
            >
              {{ user.is_active !== false ? '禁用' : '启用' }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.user-management-tab {
  max-width: 900px;
}

.tab-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.tab-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.loading-state,
.empty-state {
  color: var(--text-muted);
  font-size: 14px;
  padding: 40px 0;
  text-align: center;
}

.user-table {
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
</style>

# 查看团队 Agent 列表

列出当前团队中所有可用的 Agent 及其能力。

## 使用场景

当你需要了解团队中有哪些 Agent 可以分配任务时使用此命令。

## 调用方式

```bash
curl --fail-with-body --show-error --silent --connect-timeout 3 \
  http://localhost:${VELPOS_PORT}/api/teams/${TEAM_ID}/agents
```

## 响应格式

接口使用统一响应包装：`{"code": 0, "message": "ok", "data": [...]}`。
`data` 中每个元素包含：
- `id`: Agent 槽位唯一标识，即创建流转计划时使用的 `slot_id`
- `display_name`: Agent 显示名称
- `agent_profile_id`: Agent 角色/专长
- `description`: Agent 的职责与适用工作
- `capabilities`: Agent 随工作区注册的能力/插件列表
- `availability`: 可用状态 — "available"(可用) 或 "unstable"(不稳定)
- `is_leader`: 是否为 Leader 槽位；流转步骤只能选择非 Leader 槽位

## 示例响应

```json
{
  "code": 0,
  "message": "ok",
  "data": [
    {"id": "abc-123", "display_name": "Leader", "agent_profile_id": "product-manager", "availability": "available", "is_leader": true},
    {"id": "def-456", "display_name": "开发者", "agent_profile_id": "frontend-developer", "availability": "available", "is_leader": false}
  ]
}
```

使用非 Leader 项的 `id` 作为 `slot_id` 来创建流转计划或推进卡片。连接失败时报告
curl 的原始错误；此接口属于 Velpos 后端，不要将其描述成独立的“团队协作服务”。

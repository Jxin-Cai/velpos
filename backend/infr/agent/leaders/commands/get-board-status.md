# 查看看板状态

获取当前看板的完整状态，包括所有卡片及其执行情况。

## 使用场景

在需要了解当前工作进展、检查哪些卡片正在执行、哪些已完成时使用。

## 调用方式

```bash
curl --fail-with-body --show-error --silent --connect-timeout 3 \
  http://localhost:${VELPOS_PORT}/api/teams/${TEAM_ID}/flow/board-status
```

## 响应格式

```json
{"code": 0, "message": "ok", "data": {
  "team_id": "...",
  "slots": [{"id": "...", "display_name": "...", "agent_profile_id": "...", "availability": "available", "is_leader": false}],
  "cards": [{"id": "...", "title": "...", "status": "running", "current_slot_id": "..."}],
  "active_plans": [{"id": "...", "card_id": "...", "mode": "workflow", "status": "active",
    "steps": [{"sequence": 1, "target_slot_id": "...", "status": "running"}]}]
}}
```

用此命令检查整体进度，辅助你做出流转决策。

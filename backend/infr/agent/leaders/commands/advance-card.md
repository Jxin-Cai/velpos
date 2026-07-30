# 推进卡片（Decision 模式）

在 Decision 模式下，手动将卡片推进到下一个 Agent。

## 使用场景

当你收到子 Agent 完成通知后，根据执行结果决定下一步分配给哪个 Agent。

## 调用方式

```bash
curl --fail-with-body --show-error --silent --connect-timeout 3 \
  -X POST http://localhost:${VELPOS_PORT}/api/teams/${TEAM_ID}/flow/advance \
  -H "Content-Type: application/json" \
  -d '{
    "card_id": "CARD_ID",
    "target_slot_id": "NEXT_AGENT_SLOT_ID",
    "context": "可选：给下一个 Agent 的额外指示，基于上一步的结果"
  }'
```

## 参数说明

- `card_id`: 要推进的愿望卡 ID
- `target_slot_id`: 下一个要执行的 Agent 的 slot_id
- `context`: （可选）给下一个 Agent 的补充上下文或指示

## 注意事项

- 只能在 Decision 模式的活跃计划中使用
- 使用 /list-team-agents 确认目标 Agent 的 slot_id
- 如果所有工作已完成，使用 /complete-plan 代替此命令

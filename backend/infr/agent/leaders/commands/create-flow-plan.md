# 创建流转计划

为一张愿望卡定义执行流转计划，决定任务如何在团队 Agent 之间传递。

## 两种模式

### Workflow 模式（自动流转）

适用于：任务步骤明确、可预测的场景。系统按顺序自动流转，完成后通知你。

```bash
curl --fail-with-body --show-error --silent --connect-timeout 3 \
  -X POST http://localhost:${VELPOS_PORT}/api/teams/${TEAM_ID}/flow/plans \
  -H "Content-Type: application/json" \
  -d '{
    "card_id": "CARD_ID",
    "mode": "workflow",
    "step_slot_ids": ["SLOT_1", "SLOT_2", "SLOT_3"]
  }'
```

### Decision 模式（逐步决策）

适用于：需要根据中间结果动态调整的场景。每步完成后你会收到通知并决定下一步。

```bash
curl --fail-with-body --show-error --silent --connect-timeout 3 \
  -X POST http://localhost:${VELPOS_PORT}/api/teams/${TEAM_ID}/flow/plans \
  -H "Content-Type: application/json" \
  -d '{
    "card_id": "CARD_ID",
    "mode": "decision",
    "step_slot_ids": ["FIRST_SLOT_ID"]
  }'
```

## 决策框架

选择模式时参考：
- **Workflow**: 标准开发流程（设计→编码→测试）、确定性流水线
- **Decision**: 探索性任务、需要人工判断的工作、可能需要返工的场景

## 响应格式

```json
{"code": 0, "message": "ok", "data": {
  "id": "...",
  "status": "active",
  "mode": "workflow",
  "steps": [...]
}}
```

## 注意事项

- 创建计划后，系统会自动将卡片移动到第一个 Agent
- 一张卡同时只能有一个活跃的流转计划
- 使用 /list-team-agents 获取正确的 slot_id

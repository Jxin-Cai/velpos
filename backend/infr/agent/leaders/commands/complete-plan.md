# 完成流转计划

标记当前流转计划已完成。

## 使用场景

- Workflow 模式：所有步骤正常完成后系统自动标记，但你也可以提前手动完成
- Decision 模式：当你判断任务已达成目标，不需要更多步骤时手动标记

## 调用方式

```bash
curl --fail-with-body --show-error --silent --connect-timeout 3 \
  -X POST http://localhost:${VELPOS_PORT}/api/teams/${TEAM_ID}/flow/plans/${PLAN_ID}/complete \
  -H "Content-Type: application/json" \
  -d '{
    "summary": "简要总结本次执行的结果"
  }'
```

## 取消计划

如果需要放弃当前计划：

```bash
curl --fail-with-body --show-error --silent --connect-timeout 3 \
  -X POST http://localhost:${VELPOS_PORT}/api/teams/${TEAM_ID}/flow/plans/${PLAN_ID}/cancel \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "取消原因"
  }'
```

## 参数说明

- `PLAN_ID`: 流转计划 ID（从 /get-board-status 或创建计划时的响应中获取）
- `summary`/`reason`: 简要说明完成/取消原因

## 注意事项

- 完成后卡片状态变为 COMPLETED
- 取消后未执行的步骤会被标记为 SKIPPED

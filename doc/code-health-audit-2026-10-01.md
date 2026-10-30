# 代码健康盘点与小步优化记录

日期：2026-10-01。基线：`master@8f16d0e`，开始时工作区干净。

## 方法与边界

- 后端：Ruff 的 F401/F841/F811/F821、Vulture、Python AST 重复函数/异常处理/长度扫描；人工核对调用与副作用。
- 前端：Vue SFC 编译（包含模板）后使用 Babel 作用域引用分析，检查 JavaScript 导入关系；不因模板中没有普通文本引用就删除绑定。
- GitNexus：重新索引当前 checkout（12,775 个节点，26,669 条关系）。CLI 索引保存在 `/tmp/velpos-gitnexus-index`，未修改项目的工具配置和依赖。
- 图分析存在动态调用、跨语言引用和流程截断限制。零调用不代表死代码；接口、路由、Pydantic 校验器、历史迁移、SDK 回调保留，不能依赖扫描结果直接删除。
- 每项修改前运行 upstream impact；每步修改后验证，再处理下一项。

## 验证基线

- 前端生产构建通过，现有 Node 测试 99/99 通过。
- 后端测试通过内存 SQLite 启动：485 通过、1 跳过、1 失败。
- 原有失败：`test_accepts_legacy_ingest_token_when_request_is_local_in_dev` 使用 40 字符测试 token，但生产逻辑要求旧 token 至少 64 字符。应更新测试样本并补充短 token 拒绝边界，不放宽鉴权。
- Ruff 发现 16 项：7 个无用导入、5 个无用局部变量、1 个重复方法、3 个未定义类型引用。

## 本轮逐项处理

| 编号 | 发现 | 确认依据 | 风险与验证 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | `SessionApplicationService.commit` 定义两次 | Python 类后定义覆盖前定义，两个方法体相同 | 删除被覆盖的方法；17 个相关测试通过 | 完成 |
| 2 | `_execute_streaming` 中 4 个无用局部变量及 7 个后端无用导入 | Ruff + 源码核对；保留有副作用的调用 | 79 个相关测试通过、1 个跳过 | 完成 |
| 3 | 前端 7 个无用绑定，包括 `handleTeamNavigate`、语音 interim 累积、未使用的解构项 | Vue 模板内联编译 + Babel 作用域分析 + 全仓引用核对 | 99 个测试和生产构建通过；语音最终文本回调、停止录音检查通过 | 完成 |
| 4 | `SessionAssembler` 与 `SessionPresenter` 的恢复状态转换完全重复，SDK session ID 转换也重复 | AST 和逐行对比 | 新增 22 个契约用例，修改前后均通过；含现有相关测试共 38 个通过 | 完成 |
| 5 | `Project`、`LlmRequestQueryService`、`ExecutionTraceQueryService` 类型引用未定义 | Ruff F821 | 30 个相关测试通过；`get_type_hints` 和追踪路由 OpenAPI 构建通过 | 完成 |
| 6 | OTel 旧 token 测试样本过期，远程/关闭兼容性测试被长度校验提前拦截 | 基线失败、生产长度检查、历史改动 | 更新样本，覆盖 0/32/63/64/65 长度、IPv4/IPv6 回环、生产环境；相关测试通过 | 完成 |

保留的误报：`test_lark_message_transport.py` 的 `cache` 变量负责维持对象生命周期，直到事件循环关闭再触发析构。删除赋值会改变测试语义，故保留并添加带说明的局部 `noqa: F841`。权限快捷键仍使用 `cyclePermissionMode`，本轮仅移除页面中未使用的解构项。

## 修改前影响分析

仓库/工作区：`/Users/jxin/Desktop/Project/open-source/products/velpos`；索引基线 `8f16d0e`。

| 目标 | GitNexus 结果 | 人工核对与处理 |
| --- | --- | --- |
| 被覆盖的 `commit` | UNKNOWN，0 个已解析调用者，存在动态调用盲区 | 源码确认类中后续同名定义覆盖它；保留实际执行的方法 |
| `_execute_streaming` | LOW，1 个直接调用者 `run_claude_query`，共 3 个上游符号 | 只移除 4 个未读取的 dataclass 属性绑定 |
| `handleTeamNavigate` | UNKNOWN，0 个已解析调用者 | 全仓检索仅有定义；SFC 编译后无引用、无导出、无事件绑定 |
| `useSessionList` | UNKNOWN，0 个已解析调用者 | 从源码确认 `App.vue` 调用；仅删局部无用解构项 |
| `startRecording` | LOW，直接调用者 `toggle`，共 2 个上游符号 | 保留最终结果回调、录音启动/停止行为 |
| `_recovery_to_dict`、`_public_sdk_session_id` | CRITICAL，各 1 个直接调用者 `to_summary`，12 个上游符号、6 类受影响入口 | 修改前已明确报告高风险；先补契约测试，再委托现有相同实现；不改变外层字段 |
| `_ensure_initial_revision` 的 `Project` 类型引用 | CRITICAL，3 个直接调用者、8 个上游符号、6 类入口 | 修改前已报告；只补领域模型导入，不修改方法体 |
| 两个追踪查询依赖工厂 | UNKNOWN，未解析到调用者 | `trace_router.py` 的 `Depends` 引用明确存在；补全局类型导入后检查类型解析和路由构建 |
| OTel 测试函数、析构测试内部函数 | UNKNOWN，图没有普通调用边 | pytest 收集和 Thread target 是实际入口；只修测试数据及说明 |

图中找不到部分前端解构变量的定义，已用 SFC 编译后的 Babel 绑定引用分析确认其未使用。未据此删除被解构来源的 API 或方法。

## 后续优化清单（本轮不大范围重构）

| 问题 | 具体位置/规模 | 建议下一步 |
| --- | --- | --- |
| 静默宽泛异常捕获 | AST 发现 17 处 `except Exception` 后仅 pass/return/continue；如 `application/git_helpers.py:45`、`application/memory/memory_file_application_service.py:45`、`infr/agent/catalog.py:49,66` | 按文件补失败路径测试，识别预期异常类型，再缩窄捕获并记录堆栈；断连、取消等语义需单独验证 |
| 过长方法 | `ExecutionTraceProjector.project` 258 行；`SessionStreamConsumer.consume` 232 行；`ClaudeAgentGateway._extract_message_info` 197 行；WebSocket endpoint 195 行 | 先为事件类型/状态转换建立特征测试，每次只提取一个分支 |
| 过大模块 | `lark_adapter.py` 1649 行；`claude_agent_gateway.py` 1586 行；`session_query_engine.py` 1494 行 | 优先拆纯数据转换，后处理有生命周期和并发状态的部分 |
| 过大 Vue 文件 | `ChatPanelPage.vue` 3952 行；`WorkspacePanel.vue` 3235 行；`SettingsDialog.vue` 1712 行（含模板和样式） | 按交互边界逐个提取组件/composable，配合浏览器回归，不仅以行数为依据 |
| 前端大包 | 基线主 JS 约 2.07 MB，gzip 约 629 KB，构建提示大 chunk | 分析 PDF/Excel 等预览依赖的加载路径，再单独实施懒加载 |
| 市场服务局部重复 | Skill/MCP 服务 `_allocate_name`、`search_entries` 方法体相同 | 先明确两类市场未来差异，避免为少量重复引入泛型基类 |
| 死代码候选需人工确认 | Vulture 60% 候选中含协议方法、序列化字段、SDK 回调和迁移入口 | 路由、迁移、DTO 字段、Pydantic 校验器和动态枚举保留。已删除全仓无引用的方法、别名和未读取局部变量 |

## 结果

本轮先完成 6 个小步骤，随后又删除全仓检索确认无入口的死代码：未被调用的应用服务/仓储方法、重复别名、未读取的计数和只写不读的 stderr 缓冲，以及前端不再使用的渠道重置入口。路由、迁移、DTO 字段和动态枚举成员保留。业务代码另有测试修正、契约测试和本报告；未提交 Git commit。

- 后端全量：**515 通过、1 跳过、0 失败**，原有失败已修正。跳过项来自不承诺 message ID 的 IM 通道契约用例。
- 前端全量：**99 通过、0 失败**；生产构建成功，大包告警仍是基线已存在事项。
- `ruff check backend --select F401,F841,F811,F821`：通过；其中 1 项生命周期误报显式保留并说明。
- 前端 SFC 编译后作用域检查：0 个未引用的非参数绑定、0 个编译/解析错误（排除 `_` 前缀的有意占位变量；不等于证明所有导出和动态代码均有调用）。
- `git diff --check`：通过。
- GitNexus `detect_changes(scope=all)` 和 `detect_changes(scope=compare, base_ref=master)`：17 个已跟踪修改文件、16 个索引符号、6 条受影响流程，整体 HIGH，结构化结果无 partial/truncated 标记。
- 上述 6 条流程为会话创建、分支创建、查询、重命名、项目详情和 WebSocket 初始化中的恢复状态序列化，符合预期。基于行区间的检测会把回调删除附近的 `openMessageTrace`、解构项删除附近的 `handleEffortSelect` 一并列出；逐行 diff 已确认这两个函数体未修改。新增测试和文档为未跟踪文件，另行检查并包含在上述测试执行中。
- 未启动真实 SDK、外部 IM 通道或做浏览器端到端回归。本轮未改变页面模板/样式、协议字段、数据迁移或真实服务配置；测试结果不能保证不存在未覆盖问题。

复现核心检查：

```sh
cd backend
DATABASE_URL=sqlite+aiosqlite:///:memory: .venv/bin/python -m pytest test -q
cd ../frontend
node --test $(rg --files src -g '*.test.js')
npm run build
```

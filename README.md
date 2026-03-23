# Velpos

Velpos（意成）是一个 Claude Code 的 Web 控制台，通过 [Claude Agent SDK](https://github.com/anthropics/claude-code-sdk-python) 与 Claude Code CLI 交互，提供可视化的会话管理、项目管理、终端、IM 集成等能力。

**后端**: Python FastAPI + SQLAlchemy (async) + MySQL
**前端**: Vue 3 + Vite
**通信**: REST API + WebSocket 实时推送

---

## 功能概览

| 功能 | 说明 |
|---|---|
| **多会话管理** | 创建、删除、重命名会话，支持批量操作和搜索 |
| **项目空间** | 按目录组织会话，每个项目独立的 Claude Code 工作区 |
| **实时对话** | WebSocket 流式推送，Markdown 渲染 + 代码高亮 + 一键复制 |
| **图片/媒体输入** | 对话中可拖拽、粘贴图片发送给 Claude |
| **模型切换** | 运行时切换 Claude 模型（opus / sonnet / haiku） |
| **权限模式** | 支持 plan / autoAccept / acceptEdits / bypassPermissions 等权限模式 |
| **上下文管理** | 清除上下文 / 压缩上下文（compact） |
| **内置终端** | 在项目目录下执行终端命令，可拖拽调整大小 |
| **插件管理** | 安装 / 卸载 Claude Code MCP 插件 |
| **Agent 管理** | 加载 / 卸载预置 Agent（按项目维度） |
| **命令面板** | 查看 Claude Code slash commands |
| **Memory 管理** | 编辑项目 CLAUDE.md 和 memory 文件 |
| **Git 管理** | 全局 Git 配置（git config + SSH Key 管理） |
| **IM 集成** | 绑定飞书 / 微信 / QQ / OpenIM，双向消息同步 |
| **多渠道配置** | Channel Profile 管理不同的 API Key 和模型配置 |
| **Settings 配置** | 集中管理 Claude Code 核心设置（权限、模型、环境变量等） |
| **工作会话面板** | 查看当前活跃的 Claude 工作会话状态 |
| **通知中心** | 运行状态和异常通知 |
| **文件路径识别** | 消息中的本地文件路径可点击打开 |
| **主题切换** | Dark / Light / Sepia 三套主题 |

---

## 快速开始

### 前置条件

- **Node.js** >= 18
- **Python** >= 3.11, < 3.13
- **Docker** & Docker Compose（用于 MySQL）
- **[uv](https://docs.astral.sh/uv/)** — Python 包管理器
- **Claude Code CLI** — 已安装并可执行（`claude` 命令可用）

### 1. 克隆项目

```bash
git clone <repo-url>
cd velpos
```

### 2. 配置环境变量

```bash
cp build/dev/.env.example build/dev/.env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

编辑 `build/dev/.env`，确认以下关键配置：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `MYSQL_ROOT_PASSWORD` | `root123456` | MySQL root 密码 |
| `MYSQL_DATABASE` | `velpos` | 数据库名 |
| `MYSQL_HOST_PORT` | `3307` | MySQL 映射端口 |
| `BACKEND_PORT` | `8083` | 后端端口 |
| `FRONTEND_PORT` | `3000` | 前端端口 |
| `CLAUDE_CLI_PATH` | `/Users/jxin/.local/bin/claude` | Claude CLI 路径（**改为你本机的实际路径**） |
| `CLAUDE_PERMISSION_MODE` | `acceptEdits` | 默认权限模式 |
| `DEFAULT_MODEL` | `claude-opus-4-6` | 默认模型 |
| `PROJECTS_ROOT_DIR` | `~/claude-projects` | 项目工作目录根路径 |

编辑 `backend/.env`，确认数据库连接：

```
DATABASE_URL=mysql+aiomysql://root:root123456@localhost:3307/velpos
```

### 3. 一键启动

```bash
build/dev/start.sh start
```

该脚本会依次：
1. 启动 MySQL Docker 容器
2. 安装后端依赖并启动（`uv run uvicorn`，自动热重载）
3. 安装前端依赖并启动（`npm run dev`）
4. 自动运行数据库迁移

启动完成后：
- **前端**: http://localhost:3000
- **后端 API**: http://localhost:8083/docs（Swagger 文档）

### 服务管理

```bash
build/dev/start.sh start     # 启动全部服务
build/dev/start.sh stop      # 停止全部服务
build/dev/start.sh restart   # 重启
build/dev/start.sh status    # 查看运行状态
build/dev/start.sh logs      # 查看后端日志
```

---

## 首次使用：配置 Settings（重要）

> **启动服务后，必须先完成 Settings 配置，否则 Claude Code 内核无法正常工作。**

### 步骤 1：打开 Settings

点击页面顶栏的 **齿轮图标** 打开 Settings 对话框。

### 步骤 2：配置 Channel Profile（API 渠道）

Channel Profile 是 Claude Code 连接 API 的凭证配置，**至少需要创建一个并激活**。

1. 点击 **Add Channel** 按钮
2. 填写以下信息：
   - **Name** — 渠道名称（如 `Production`）
   - **Host** — API 地址（留空则使用默认 `https://api.anthropic.com`）
   - **API Key** — 你的 Anthropic API Key（`sk-ant-...`）
   - **Auth Env Variable** — 认证环境变量名（默认 `ANTHROPIC_API_KEY`）
3. （可选）配置模型映射：点击 **Fetch Models** 获取可用模型列表，为 Default Model / Opus / Sonnet / Haiku 指定具体模型
4. 点击 **Create** 创建
5. 点击渠道卡片上的 **Activate** 按钮激活该渠道

> 你可以创建多个 Channel Profile（如生产环境、测试环境、第三方中转），随时切换激活。

### 步骤 3：调整 Settings Configuration

在 Settings 对话框下方的 **Settings Configuration** 区域，根据需要调整：

| 设置项 | 说明 |
|---|---|
| **Permission Mode** | 权限模式：`Default` 每次询问、`Accept Edits` 自动接受编辑、`Plan` 仅规划不执行、`Bypass` 全自动 |
| **Completed Onboarding** | 跳过首次引导流程 |
| **Effort Level** | 推理深度：Low 快速低成本、Medium 平衡、High 深度推理 |
| **Skip Dangerous Mode Prompt** | 跳过进入 Bypass 模式时的安全确认 |
| **Disable Non-Essential Traffic** | 禁用更新检查、遥测等非核心网络请求 |
| **Agent Teams** | 实验性功能：启用多 Agent 协作 |
| **Tool Search** | 启用 MCP 工具搜索和动态加载 |
| **Attribution** | 配置 commit 和 PR 中的署名文本 |

点击底部 **Save** 保存配置。

### 步骤 4：开始使用

配置完成后，创建项目和会话即可开始与 Claude Code 对话。

---

## 使用指南

### 创建项目和会话

1. 打开 http://localhost:3000
2. 点击侧边栏顶部 **+** 创建项目，指定项目名称和工作目录
3. 在项目下创建会话，即可与 Claude Code 对话

### 对话交互

- 输入框输入消息后回车发送
- 支持 **拖拽/粘贴图片** 一并发送
- Claude 回复会实时流式展示，包含 Markdown、代码高亮
- 代码块右上角 **复制按钮** 一键复制代码
- 消息中的 **本地文件路径** 自动识别为可点击链接

### 模型和权限

- 顶栏下拉切换 Claude 模型（opus / sonnet / haiku）
- 权限模式控制 Claude 对文件的操作权限：
  - `Plan` — 仅规划，不执行
  - `Accept Edits` — 自动接受编辑，其他操作需确认
  - `Auto Accept` — 全自动
  - `Bypass` — 跳过所有权限检查

### 内置终端

- 点击顶栏终端图标打开右侧终端面板
- 命令在当前项目目录下执行
- 左边缘可 **拖拽调整** 终端宽度

### 插件管理

点击顶栏插件图标，可安装/卸载 Claude Code 的 MCP 插件（如 GitHub、Playwright 等）。

### Agent 管理

在项目设置中可加载预置 Agent，Agent 会作为 system prompt 注入到 Claude 对话中。

### Memory 管理

- 编辑项目级 `CLAUDE.md` 文件，定义 Claude 的行为准则
- 管理 memory 文件，持久化项目知识

### Git 管理

通过 Settings 或专用入口管理全局 Git 配置：
- 设置 `user.name` 和 `user.email`
- 管理 SSH Key（生成、查看、复制公钥）

### IM 绑定

支持将会话绑定到 IM 渠道，实现双向消息同步：

| 渠道 | 绑定方式 | 说明 |
|---|---|---|
| **飞书 (Lark)** | 扫码登录 | 通过飞书机器人收发消息 |
| **微信 (WeChat)** | 扫码登录 | 通过微信账号收发消息 |
| **QQ** | 凭证配置 | 需要 QQ 机器人的 app_id 和 app_secret |
| **OpenIM** | 凭证配置 | 自建 OpenIM 服务器 |

绑定步骤：
1. 在 IM 管理中创建渠道实例并完成初始化
2. 在会话详情中点击 **绑定 IM**，扫码或选择渠道
3. 绑定后，IM 中的消息会转发到 Claude，Claude 的回复也会同步到 IM

### Channel Profile

管理多个 API 渠道配置（不同的 API Key、Base URL、默认模型），可按需切换。

### 工作会话面板

点击顶栏查看当前所有活跃的 Claude 工作会话，实时监控会话状态。

### 命令面板

查看 Claude Code 支持的 slash commands 列表，快速了解可用指令。

---

## 生产部署

生产环境使用全 Docker 方案，包含 MySQL + Backend + Frontend (nginx) 三个服务。

```bash
cp build/prod/.env.example build/prod/.env
```

编辑 `build/prod/.env`，配置以下关键变量：

| 变量 | 说明 |
|---|---|
| `APP_PORT` | 对外暴露端口（默认 80） |
| `MYSQL_ROOT_PASSWORD` | MySQL 密码 |
| `CLAUDE_CLI_PATH` | 容器内 Claude CLI 路径 |
| `ANTHROPIC_API_KEY` | Anthropic API Key |
| `PROJECTS_HOST_DIR` | 宿主机上的项目目录（会 bind mount 到容器） |

```bash
cd build/prod
docker compose up --build -d
```

> 生产环境同样需要在启动后通过 Web 界面完成 Settings 配置。

---

## 数据库迁移

后端启动时自动执行 Alembic 迁移。手动操作：

```bash
cd backend

# 生成迁移
uv run alembic revision --autogenerate -m "description"

# 执行迁移
uv run alembic upgrade head
```

---

## 项目结构

```
velpos/
├── backend/                  # Python FastAPI 后端
│   ├── domain/               # 领域层 -- 纯业务逻辑
│   │   ├── session/          # 会话聚合根
│   │   ├── project/          # 项目聚合根
│   │   ├── im_binding/       # IM 绑定 + 渠道注册
│   │   └── channel_profile/  # 渠道配置
│   ├── application/          # 应用层 -- 用例编排
│   ├── infr/                 # 基础设施层
│   │   ├── config/           # 数据库、IM 配置
│   │   ├── repository/       # 仓储实现 + ORM 模型
│   │   ├── client/           # Claude SDK 网关、终端执行器等
│   │   └── im/               # IM 适配器 (lark/weixin/qq/openim)
│   ├── ohs/                  # 开放主机服务层
│   │   ├── http/             # REST 路由 + DTO
│   │   └── ws/               # WebSocket 路由
│   └── alembic/              # 数据库迁移
├── frontend/                 # Vue 3 前端
│   └── src/
│       ├── app/              # 应用入口、路由、全局样式
│       ├── pages/            # 页面组件
│       ├── features/         # 功能模块（18 个独立 feature）
│       ├── entities/         # 核心业务数据 (session/project)
│       └── shared/           # 共享工具、HTTP/WS 客户端
└── build/
    ├── dev/                  # 开发环境（Docker MySQL + 本地服务）
    ├── prod/                 # 生产环境（全 Docker）
    └── docker/               # 共享 MySQL 初始化脚本
```

---

## 端口说明

| 服务 | 开发端口 | 生产端口 |
|---|---|---|
| 前端 | 3000 | 80（nginx） |
| 后端 API | 8083 | 8083（内部） |
| MySQL | 3307（宿主机） | 3306（内部） |

---

## 技术栈

- **后端**: Python 3.11+, FastAPI, SQLAlchemy (async), Alembic, Claude Agent SDK, aiomysql
- **前端**: Vue 3 (Composition API), Vite 8, marked, highlight.js
- **数据库**: MySQL 8
- **IM SDK**: lark-oapi (飞书), httpx (微信/QQ/OpenIM)
- **包管理**: uv (后端), npm (前端)

<div align="center">

# Velpos

**在 Claude Code 之上打包 AI Agent：身份、SOP 与工具一体化封装。**

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3-4FC08D.svg?logo=vuedotjs&logoColor=white)](https://vuejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Claude](https://img.shields.io/badge/Claude_Code-Agent_SDK-D97757.svg)](https://github.com/anthropics/claude-code-sdk-python)

[English](./README.md)&ensp;|&ensp;[许可证](./LICENSE)&ensp;|&ensp;[行为准则](./CODE_OF_CONDUCT.md)

</div>

<br/>

Velpos（意成）是一个基于 [Claude Agent SDK](https://github.com/anthropics/claude-code-sdk-python) 的 [Claude Code](https://github.com/anthropics/claude-code) Web 控制台。它的核心价值是 **Agent 打包能力**——把可复用的 AI 助手封装成可配置单元，统一承载 **身份定义**、**借助插件实现的 SOP** 以及 **工具能力封装**。

这使得 **非技术人员** 也能更容易地构建和运营多 Agent AI 助手——无需手写 prompt、手动拼工具链，或维护脆弱的命令流程。

<br/>

## 目录

- [为什么需要 Agent 打包](#为什么需要-agent-打包)
- [亮点能力](#亮点能力)
- [部署](#部署)
  - [开发环境](#开发环境)
  - [生产环境](#生产环境)
- [首次使用配置](#首次使用配置)
- [使用概览](#使用概览)
- [架构概览](#架构概览)
- [技术栈](#技术栈)
- [参与贡献](#参与贡献)
- [许可证](#许可证)

<br/>

## 为什么需要 Agent 打包

很多 AI 助手方案最后不好用，不是因为模型不够强，而是因为真正的运行知识散落在 prompt、工具权限、插件配置和口口相传的流程习惯里。

Velpos 把这些分散的部分打包成可复用能力：

| 层面 | 作用 |
|---|---|
| **身份** | 定义 Agent 是谁、承担什么角色、应该如何行动 |
| **SOP** | 把重复流程沉淀下来，让 Agent 按稳定步骤执行，而非临场发挥 |
| **工具** | 借助插件暴露合适的能力，最终用户无需自己拼装工具链 |
| **复用** | 同一个打包好的 Agent 可以跨项目、跨团队、跨场景复用，减少能力漂移 |

这对 **产品经理、运营、客服、创始人** 等非技术人员尤其有价值——他们需要的是稳定可用的助手，而不是自己成为 prompt 工程师。

<br/>

## 亮点能力

### Agent 打包

- **Agent 封装** — 把身份、职责边界和行为预期打包成可复用单元
- **插件驱动的 SOP** — 把重复工作流沉淀成稳定操作流程，而非依赖临场 prompt
- **工具封装** — 通过插件隐藏底层工具接线，让最终用户按任务使用能力
- **多 Agent 协作** — 组合多个已打包 Agent，形成分工明确的协作式 AI 助手团队

### 平台能力

- **项目工作区** — 按目录组织会话，隔离 Claude Code 工作空间
- **流式对话** — 基于 WebSocket 的实时响应，支持 Markdown 和代码高亮
- **内置终端** — 在项目目录下直接执行命令
- **插件管理** — 安装 / 卸载 Claude Code MCP 插件
- **Memory 管理** — 在 UI 中编辑 `CLAUDE.md` 与 memory 文件
- **Git 管理** — 配置身份和 SSH Key
- **IM 集成** — 连接飞书、微信、QQ、OpenIM，双向消息同步
- **Channel Profile** — 管理多套 API Key、Host 和模型映射
- **Settings 中心** — 集中管理 Claude Code 核心配置

<br/>

## 部署

```bash
git clone git@github.com:Jxin-Cai/velpos.git
cd velpos
```

### 开发环境

> 仅 MySQL 运行在 Docker 中。后端和前端运行在 **宿主机**，直接管理 **宿主机文件系统** 上的项目目录。

**前置条件：** Node.js >= 18、Python >= 3.11、Docker、[uv](https://docs.astral.sh/uv/)、Claude Code CLI（`claude` 命令可用）

**1. 配置**

```bash
cp build/dev/.env.example build/dev/.env
```

所有开发环境配置都在这一个文件中。编辑 `CLAUDE_CLI_PATH` 为你本机的 Claude CLI 路径。

<details>
<summary><b>build/dev/.env</b></summary>

| 变量 | 默认值 | 说明 |
|---|---|---|
| `MYSQL_ROOT_PASSWORD` | `root123456` | MySQL root 密码 |
| `MYSQL_DATABASE` | `velpos` | 数据库名 |
| `MYSQL_HOST_PORT` | `3307` | MySQL 映射到宿主机的端口 |
| `DATABASE_URL` | `mysql+aiomysql://root:root123456@localhost:3307/velpos` | 后端数据库连接（需与上面 MySQL 配置一致） |
| `BACKEND_PORT` | `8083` | 后端端口 |
| `FRONTEND_PORT` | `3000` | 前端端口 |
| `CLAUDE_CLI_PATH` | `/usr/local/bin/claude` | 宿主机上 `claude` 可执行文件路径 |
| `CLAUDE_PERMISSION_MODE` | `acceptEdits` | 默认权限模式 |
| `DEFAULT_MODEL` | `claude-opus-4-6` | 默认模型 |
| `PROJECTS_ROOT_DIR` | `~/claude-projects` | **宿主机文件系统**上的项目根目录 |
| `CORS_ALLOW_ORIGINS` | `*` | 允许的浏览器来源 |

</details>

**2. 启动**

```bash
build/dev/start.sh start
```

脚本会启动 MySQL（Docker）、后端（宿主机 `uv run uvicorn`）和前端（宿主机 `npm run dev`）。数据库迁移在后端启动时自动执行。

| 服务 | 地址 |
|---|---|
| 前端 | http://localhost:3000 |
| API 文档 | http://localhost:8083/docs |

<details>
<summary><b>服务管理</b></summary>

```bash
build/dev/start.sh start     # 启动全部
build/dev/start.sh stop      # 停止全部
build/dev/start.sh restart   # 重启全部
build/dev/start.sh status    # 查看状态
build/dev/start.sh logs      # 查看后端日志
```

</details>

### 生产环境

> 所有服务运行在 Docker 中（MySQL + 后端 + 前端/nginx）。后端管理的是 **容器内** 的文件目录。宿主机目录通过 bind mount 挂载进容器以持久化项目数据。

**1. 配置**

```bash
cp build/prod/.env.example build/prod/.env
```

<details>
<summary><b>build/prod/.env — 统一配置</b></summary>

| 变量 | 默认值 | 说明 |
|---|---|---|
| `MYSQL_ROOT_PASSWORD` | — | MySQL root 密码 |
| `MYSQL_DATABASE` | `velpos` | 数据库名 |
| `APP_PORT` | `80` | nginx 对外暴露端口 |
| `PROJECTS_HOST_DIR` | `~/.agent_projects` | 宿主机目录，挂载到容器的 `/data/projects` |
| `ANTHROPIC_API_KEY` | — | Anthropic API Key |
| `CLAUDE_PERMISSION_MODE` | `acceptEdits` | 默认权限模式 |
| `DEFAULT_MODEL` | `claude-opus-4-6` | 默认模型 |

以下变量由 docker-compose **自动配置**，无需手动设置：

| 变量 | 固定值 | 原因 |
|---|---|---|
| `DATABASE_URL` | `mysql+aiomysql://root:...@mysql:3306/velpos` | 容器间网络互通 |
| `CLAUDE_CLI_PATH` | `/usr/local/bin/claude` | 在后端镜像中已安装 |
| `PROJECTS_ROOT_DIR` | `/data/projects` | 容器内挂载点 |

</details>

**2. 构建并启动**

```bash
cd build/prod
docker compose up --build -d
```

栈包含 MySQL、后端和前端（nginx）。通过 `http://localhost`（或你配置的端口）访问界面。

<br/>

## 首次使用配置

> **重要提示：** 启动服务后，需要先在 Web 界面完成设置，Claude Code 会话才能正常工作。

**1.** 点击顶部 **齿轮图标** 打开 Settings。

**2.** 创建 **Channel Profile**（API 地址 + Key + 模型映射）：

&emsp;&emsp;Add Channel &#8594; 填写 Name、Host、API Key &#8594; Create &#8594; Activate

**3.** 检查 **Settings Configuration**：

<details>
<summary><b>可用设置项</b></summary>

| 设置项 | 说明 |
|---|---|
| **Permission Mode** | Default / Accept Edits / Plan / Bypass |
| **Completed Onboarding** | 跳过首次引导 |
| **Effort Level** | Low / Medium / High 推理深度 |
| **Skip Dangerous Mode Prompt** | 跳过 bypass 模式额外确认 |
| **Disable Non-Essential Traffic** | 关闭非核心网络请求 |
| **Agent Teams** | 实验性多 Agent 支持 |
| **Tool Search** | 启用 MCP 工具搜索与动态加载 |
| **Attribution** | 配置 commit / PR 署名文本 |

</details>

**4.** 创建项目、创建会话，**加载已打包的 Agent**，开始协作。

<br/>

## 使用概览

| 功能 | 说明 |
|---|---|
| **项目与会话** | 从侧边栏创建项目，指定目录，管理会话 |
| **对话** | 发送消息，粘贴/拖拽图片，流式 Markdown + 代码高亮 |
| **模型与权限** | 顶部栏切换模型，选择权限模式控制自主程度 |
| **终端** | 打开内置终端，在项目目录执行命令 |
| **插件与 Agent** | 安装 MCP 插件，加载项目级已打包 Agent |
| **Memory** | 直接在 UI 中编辑 `CLAUDE.md` 与 memory 文件 |
| **Git** | 管理全局 Git 身份和 SSH Key |
| **IM 集成** | 绑定 **飞书**、**微信**、**QQ** 或 **OpenIM**，双向消息同步 |

<br/>

## 架构概览

```text
velpos/
├── backend/                  # Python FastAPI
│   ├── domain/               # 领域层 — 纯业务逻辑
│   ├── application/          # 应用服务 — 用例编排
│   ├── infr/                 # 基础设施 — 仓储、客户端、适配器
│   ├── ohs/                  # 开放主机服务 — REST + WebSocket
│   └── alembic/              # 数据库迁移
├── frontend/                 # Vue 3 + Vite
│   └── src/
│       ├── app/              # 应用壳、路由、启动
│       ├── pages/            # 路由级页面
│       ├── features/         # 独立功能模块
│       ├── entities/         # 核心业务数据
│       └── shared/           # 工具、HTTP/WS 客户端
└── build/
    ├── dev/                  # 开发：Docker MySQL + 宿主机服务
    └── prod/                 # 生产：全 Docker 栈
```

后端采用 **DDD 四层架构**，前端采用 **Feature-Sliced** 结构。

<br/>

## 技术栈

| 层面 | 技术 |
|---|---|
| 后端 | Python, FastAPI, SQLAlchemy (async), Alembic, Claude Agent SDK, aiomysql |
| 前端 | Vue 3, Vite, marked, highlight.js |
| 数据库 | MySQL 8 |
| 包管理 | uv (后端), npm (前端) |

<br/>

## 参与贡献

参与前请先阅读 [行为准则](./CODE_OF_CONDUCT.md)。

如果你计划提交较大的改动，**请先开 issue 讨论方向和范围**。欢迎 Bug 反馈、功能建议和 Pull Request。

## 许可证

本项目采用 [Apache License 2.0](./LICENSE)。

Copyright 2026 jxin

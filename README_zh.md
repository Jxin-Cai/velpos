<div align="center">

# Velpos

**在 Claude Code 之上打包 AI Agent：身份、SOP 与工具一体化封装。**

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3-4FC08D.svg?logo=vuedotjs&logoColor=white)](https://vuejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Claude](https://img.shields.io/badge/Claude_Code-Agent_SDK-D97757.svg)](https://github.com/anthropics/claude-code-sdk-python)

[English](./README.md)&ensp;|&ensp;[演示视频](https://www.bilibili.com/video/BV1iEDhBuEVZ/)&ensp;|&ensp;[许可证](./LICENSE)&ensp;|&ensp;[行为准则](./CODE_OF_CONDUCT.md)

</div>

<br/>

Velpos（意成）是一个基于 [Claude Agent SDK](https://github.com/anthropics/claude-code-sdk-python) 的 [Claude Code](https://github.com/anthropics/claude-code) Web 控制台。它的核心价值是 **Agent 打包能力**——把可复用的 AI 助手封装成可配置单元，统一承载 **身份定义**、**借助插件实现的 SOP** 以及 **工具能力封装**。

这使得 **非技术人员** 也能更容易地构建和运营多 Agent AI 助手——无需手写 prompt、手动拼工具链，或维护脆弱的命令流程。

过去一个月，Velpos 已经从“Claude Code 的聊天式外壳”演进为一个 **项目运营控制台**：它可以管理项目与会话、执行定时任务、分支并比较多条尝试路径、追踪任务进度、查看工作区历史、接入 IM 渠道，并把整个工作流收束到浏览器里。

<br/>

## 目录

- [为什么需要 Agent 打包](#为什么需要-agent-打包)
- [亮点能力](#亮点能力)
- [近期更新](#近期更新)
- [快捷键操作](#快捷键操作)
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
- **Marketplace 刷新** — 安装已打包 Agent 前自动刷新插件市场信息，让项目使用最新工具定义

### 项目运营

- **项目工作区** — 从本地目录创建项目，按项目组织会话，并把 Claude Code 的工作范围限定在当前工作区
- **流式对话** — 基于 WebSocket 的实时响应，支持 Markdown、代码高亮、权限请求和用户选择
- **附件能力** — 将图片/文件发送到会话，并在对话中保留附件记录
- **任务进度** — 内联渲染 `TodoWrite`，展示 run steps 与 timeline events，让 Claude Code 的执行过程可见
- **内置终端** — 基于 xterm 的抽屉式终端，可在当前项目目录直接执行命令
- **工作区历史** — 查看近期工作区变更、浏览文件版本、比较分支间的消息与代码差异
- **Memory 管理** — 在 UI 中编辑 `CLAUDE.md`、memory 文件和项目记忆条目
- **Settings 中心** — 集中管理 Claude Code 设置、Channel Profile、模型映射、权限模式和输入偏好

### 治理与协作

- **插件管理** — 在浏览器中安装 / 卸载 Claude Code MCP 插件
- **Git 管理** — 配置 Claude Code 项目工作所需的 Git 身份和 SSH Key
- **IM 集成** — 连接飞书、微信、QQ、OpenIM，支持会话双向同步和远程操控
- **Project Clock 定时任务** — 为每次任务选择指定 IM 渠道实例，执行会话自动绑定、结束后自动断开，并可在成功后删除一次性会话
- **多会话分支** — 从同一上下文创建多个会话分支，可选 Git worktree 隔离，支持消息/代码差异对比并让 Claude 分析取舍
- **分支收敛** — 选择一个目标会话保留，删除其他会话；worktree 目标只合并已提交内容回主干并清理 worktree
- **用量治理** — 跟踪 token 使用与预算策略状态，提升会话级成本可见性
- **Evolution 提案** — 将项目改进建议和演化想法沉淀为可管理记录

<br/>

## 近期更新

2026 年 4 月的开发重点，是让 Velpos 能够支撑真实的日常项目运营：

| 领域 | 更新内容 | 对使用者的价值 |
|---|---|---|
| 项目启动 | 开发/生产配置统一收敛到 `build/dev/.env` 与 `build/prod/.env`；开发启动脚本自动从 PATH 探测 `claude` | 配置文件更少，首次启动更顺滑 |
| 会话稳定性 | 会话执行状态按 session 隔离，WebSocket 连接池统一，数据库提交更及时释放锁 | 长任务和多会话切换更稳定 |
| 任务可视化 | 增加内联 `TodoWrite`、任务进度面板、run steps 和 timeline events | 用户能看到 Claude Code 正在做什么，而不是盲等结果 |
| 定时任务 | Project Clock 支持周期执行、指定 IM 渠道发送、自动解绑、成功后清理一次性会话 | 可安全委托重复性的项目工作 |
| 分支治理 | 增加多会话分支、可选 worktree 隔离、分支对比和收敛流程 | 可以并行探索多个方案，再保留最优路径 |
| 工作区 | 工作区面板增强项目历史、文件版本对比和按会话目录显示 Git 分支 | 不离开浏览器也能理解项目发生了什么变化 |
| Memory 与演化 | 增加项目记忆条目、`CLAUDE.md` 修订流和 Evolution 提案 | 项目知识和改进想法不再散落在聊天记录里 |
| 输入与快捷键 | 增加全局快捷键、会话导航、权限模式循环、快捷键提示、输入法安全发送和 Enter 行为偏好 | 键盘操作更快，也更不容易误发 |
| UI 体验 | 侧边栏、弹窗、设置、终端、通知、消息列表和启动动画整体打磨 | 控制台视觉更统一，日常操作更顺手 |

<br/>

## 当前正式版本：v0.2.0

v0.2.0 是首个围绕项目运营与分支治理完善的正式版本，当前具备：

- 基于 Claude Code Agent SDK 的可视化 Agent 打包与运行控制台
- 项目/会话管理、流式对话、附件、模型切换、权限模式和上下文工具
- 飞书、微信、QQ、OpenIM 渠道实例管理与会话双向同步
- 定时项目任务：指定 IM 发送渠道、自动解绑、成功后可清理一次性执行会话
- 多会话分支：支持可选 worktree 隔离，并按会话目录正确显示当前 Git 分支
- 会话差异分析：消息差异、Git 代码 diff 摘要，以及可直接发送给 Claude 的分析 prompt
- 目标会话收敛：删除备选会话，安全地将已提交 worktree 分支合并回主干

<br/>

## 快捷键操作

Velpos 提供完整的键盘快捷键体系，支持高效导航与操控。

### 全局快捷键

| 快捷键 | 功能 |
|---|---|
| `ESC` | 关闭最顶层弹窗；无弹窗时取消正在运行的查询 |
| `Cmd/Ctrl + ↑` | 切换到上一个会话 |
| `Cmd/Ctrl + ↓` | 切换到下一个会话 |
| `Cmd/Ctrl + P` | 打开设置 |
| `Cmd/Ctrl + B` | 折叠/展开侧边栏 |
| `Cmd/Ctrl + K` | 切换语音输入 |
| `Shift + Tab` | 循环切换权限模式 |

### 对话输入

| 快捷键 | 功能 |
|---|---|
| `Enter` | 默认输入模式下发送消息 |
| `Ctrl/Cmd + Enter` | 默认输入模式下换行；备用模式下发送消息 |

Velpos 也会保护输入法组合态：中文/日文/韩文输入法选词时按 `Enter` 不会误发消息。

### 工作区面板

| 快捷键 | 功能 |
|---|---|
| `← / →` | 在对比模式下浏览文件版本 |

### 弹窗操作

所有弹窗（设置、定时任务、Memory、Evolution、插件、Agent、Git、IM）均支持 `ESC` 关闭。快捷键系统采用优先级派发机制——弹窗始终优先于全局处理器。

<br/>

## 部署

```bash
git clone git@github.com:Jxin-Cai/velpos.git
cd velpos
```

### 开发环境

> 仅 MySQL 运行在 Docker 中。后端和前端运行在 **宿主机**，直接管理 **宿主机文件系统** 上的项目目录。

**前置条件：** Node.js >= 18、Python >= 3.11、Docker、[uv](https://docs.astral.sh/uv/)、Claude Code CLI（`claude` 命令可用）

<details>
<summary><b>安装前置依赖</b></summary>

```bash
# Docker — https://docs.docker.com/get-docker/

# Python >= 3.11 — https://www.python.org/downloads/
python3 --version

# uv（Python 包管理器）
curl -LsSf https://astral.sh/uv/install.sh | sh

# Node.js >= 18 — https://nodejs.org/
node -v && npm -v

# Claude Code CLI
npm install -g @anthropic-ai/claude-code
```

启动脚本会自动检查所有前置依赖，缺失时会显示对应的安装命令。

</details>

**1. 配置**

```bash
cp build/dev/.env.example build/dev/.env
```

所有开发环境配置都在这一个文件中。`CLAUDE_CLI_PATH` 会在启动时从 PATH 中 **自动探测**，一般不需要手动设置。

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
| `CLAUDE_CLI_PATH` | *（自动探测）* | 仅当 `claude` 不在 PATH 中时需手动设置 |
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

**4.** 从本地目录或 `PROJECTS_ROOT_DIR` 下的新路径创建项目。

**5.** 创建会话，选择模型与权限模式，**加载已打包的 Agent**，开始协作。

<br/>

## 使用概览

### 核心功能

![Velpos 核心功能](./doc/features-zh.png)

### 用户旅程

![Velpos 用户旅程](./doc/journey-zh.png)

| 功能 | 说明 |
|---|---|
| **项目与会话** | 从侧边栏创建项目，指定目录，创建/导入会话，置顶重要项目，并用快捷键切换会话 |
| **对话** | 发送消息，粘贴/拖拽图片，查看流式 Markdown 与代码高亮，响应权限请求，并监控内联任务进度 |
| **模型与权限** | 顶部栏切换模型，选择权限模式控制自主程度，并用 `Shift + Tab` 快速循环切换 |
| **终端** | 打开内置终端，在项目目录执行命令，让终端操作和对话上下文并排存在 |
| **工作区** | 查看项目历史、检查生成文件、比较文件版本，并理解不同会话分支对代码的影响 |
| **插件与 Agent** | 安装 MCP 插件，刷新基于 marketplace 的已打包 Agent，并加载项目级 Agent 处理专业任务 |
| **Memory** | 直接在 UI 中编辑 `CLAUDE.md`、项目记忆条目和修订记录 |
| **Git** | 管理 Claude Code 会话使用的全局 Git 身份和 SSH Key |
| **IM 集成** | 绑定 **飞书**、**微信**、**QQ** 或 **OpenIM**，支持双向消息同步和远程操控 |
| **定时任务** | 定期运行项目任务，指定 IM 渠道实例发送通知，完成后自动解绑，并可清理成功的一次性执行会话 |
| **多会话分支** | 创建多个会话分支，用 worktree 隔离，比较消息/代码差异，让 Claude 分析取舍，并收敛到目标会话 |
| **Evolution** | 记录项目改进提案，让反复出现的演进想法不再沉没在聊天历史中 |

### 典型使用流程

1. 执行 `build/dev/start.sh start` 启动开发栈，打开 Web 控制台。
2. 配置并激活 Channel Profile，确认模型映射可用。
3. 创建或选择项目目录，然后创建 Claude Code 会话。
4. 根据任务加载合适的已打包 Agent 或插件。
5. 通过对话推进工作，同时观察任务进度、timeline events、终端输出和工作区变更。
6. 遇到不确定方案时，创建多个会话分支并行探索，对比结果后收敛到最优会话。
7. 对重复性工作，创建 Project Clock 定时任务，并把进展推送到指定 IM 渠道。

<br/>

## 架构概览

![Velpos 架构概览](./doc/architecture-zh.png)

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
| 前端 | Vue 3, Vite, marked, highlight.js, DOMPurify, xterm.js |
| 数据库 | MySQL 8 |
| 包管理 | uv (后端), npm (前端) |

<br/>

## 参与贡献

参与前请先阅读 [行为准则](./CODE_OF_CONDUCT.md)。

如果你计划提交较大的改动，**请先开 issue 讨论方向和范围**。欢迎 Bug 反馈、功能建议和 Pull Request。

## 许可证

本项目采用 [Apache License 2.0](./LICENSE)。

Copyright 2026 jxin

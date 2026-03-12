# dbot

一个用 Python 构建的轻量级个人 AI 助手框架。连接到飞书/Lark 消息平台，通过模块化、可扩展的架构提供 AI 辅助服务。

[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## 功能特性

- **飞书/Lark 支持** - 连接飞书/Lark 消息平台
- **LLM 提供商** - 支持本地 Ollama 和 OpenAI、Anthropic 兼容格式的任何模型提供商
- **工具系统** - 可扩展的文件操作、网页搜索、Shell 执行等工具
- **技能系统** - 模块化技能，支持 specialized 功能
- **记忆管理** - 持久化对话历史，上下文感知响应
- **会话管理** - 多用户支持，隔离会话
- **定时任务** - 计划任务和提醒
- **MCP 协议** - Model Context Protocol，支持外部工具集成

## 安装

```bash
pip install dbot
```

开发安装：

```bash
git clone https://github.com/yeziyun/dbot.git
cd dbot
pip install -e ".[dev]"
```

## 快速开始

### 1. 启动网关

```bash
python run.py
```

首次运行时会自动创建：
- `./config.json` 配置文件
- `./workspace/` 工作目录

### 2. 配置 LLM 提供商

编辑 `./config.json` 添加 API 密钥：

```json
{
  "providers": {
    "anthropic": {
      "api_key": "your-anthropic-api-key"
    },
    "openai": {
      "api_key": "your-openai-api-key"
    }
  },
  "agents": {
    "defaults": {
      "model": "anthropic/claude-opus-4-5",
      "temperature": 0.1,
      "max_tokens": 8192
    }
  }
}
```

### 3. 配置飞书渠道

在 `./config.json` 中启用并配置飞书渠道：

```json
{
  "channels": {
    "feishu": {
      "enabled": true,
      "app_id": "your-feishu-app-id",
      "app_secret": "your-feishu-app-secret"
    }
  }
}
```

网关默认运行在端口 18790。

## 支持的 LLM 提供商

- **本地部署** - Ollama、vLLM
- **OpenAI 兼容** - 任何 OpenAI API 格式的提供商
- **Anthropic 兼容** - 任何 Anthropic Claude API 格式的提供商

## 支持的渠道

| 渠道 | 说明 |
|------|------|
| **飞书/Lark** | WebSocket 长连接 |

## 内置技能

| 技能 | 说明 |
|------|------|
| `github` | 使用 `gh` CLI 与 GitHub 仓库交互 |
| `weather` | 使用 wttr.in 和 Open-Meteo 获取天气信息 |
| `summarize` | 摘要 URL、文件和 YouTube 视频 |
| `tmux` | 远程控制 tmux 会话 |
| `clawhub` | 从 ClawHub 注册表搜索和安装技能 |
| `skill-creator` | 创建新技能 |

## 工具

dbot 提供全面的工具系统：

- **文件工具** - 在工作区读取、写入、编辑文件
- **Web 工具** - 搜索网页、获取 URL 内容
- **Shell 工具** - 执行命令（带安全限制）
- **Cron 工具** - 调度和管理重复任务
- **消息工具** - 发送跨平台消息
- **记忆工具** - 访问持久化对话记忆

## 配置

配置存储在 `./config.json`：

```json
{
  "agents": {
    "defaults": {
      "model": "anthropic/claude-opus-4-5",
      "temperature": 0.1,
      "max_tokens": 8192,
      "workspace": "./workspace"
    }
  },
  "channels": {
    "feishu": {
      "enabled": false,
      "app_id": "",
      "app_secret": ""
    }
  },
  "providers": {
    "anthropic": {
      "api_key": ""
    },
    "openai": {
      "api_key": ""
    }
  },
  "tools": {
    "restrict_to_workspace": true
  }
}
```

### 安全选项

- `restrict_to_workspace` - 限制文件操作在工作区目录内
- `blocked_patterns` - 阻止的命令正则模式
- 渠道特定的用户访问控制白名单

## 架构

```
dbot/
├── agent/          # 核心代理功能
│   ├── loop.py     # 主处理引擎
│   ├── context.py  # 上下文构建
│   ├── memory.py   # 记忆管理
│   └── tools/      # 可用工具
├── channels/       # 消息平台集成
├── providers/      # LLM 提供商支持
├── bus/            # 消息队列系统
├── config/         # 配置管理
├── skills/         # 可扩展技能系统
├── templates/      # AI 行为模板文件
├── gateway.py      # 网关启动逻辑
└── __main__.py     # 模块入口
```

### 消息总线

消息总线将渠道与代理解耦：

1. 渠道接收消息并推送到入站队列
2. 代理循环从队列处理消息
3. 响应被推送到出站队列
4. 渠道将响应发送回各自平台

### 模板

`./workspace/` 中的模板指导 AI 行为：

- `SOUL.md` - 个性和价值观
- `AGENTS.md` - 代理指令
- `HEARTBEAT.md` - 定期任务
- `MEMORY.md` - 持久化记忆
- `USER.md` - 用户偏好

## 开发

### 运行测试

```bash
pytest
```

### 代码风格

```bash
ruff check .
ruff format .
```

## 许可证

MIT 许可证 - 详见 [LICENSE](LICENSE)。

## 致谢

技能系统改编自 [OpenClaw](https://github.com/openclaw/openclaw) 的技能系统。技能格式和元数据结构遵循 OpenClaw 的约定以保持兼容性。

## 贡献

欢迎贡献！请随时提交 Pull Request。

# dbot

A lightweight personal AI assistant framework built in Python. Connect to Feishu/Lark messaging platform and provide AI-powered assistance through a modular, extensible architecture.

[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## Features

- **Feishu/Lark Support** - Connect to Feishu/Lark messaging platform
- **Multiple LLM Providers** - Support for OpenAI, Anthropic, DeepSeek, Groq, OpenRouter, Zhipu, Gemini, and more
- **Tool System** - Extensible tools for file operations, web search, shell execution, and more
- **Skills System** - Modular skills for specialized functionality
- **Memory Management** - Persistent conversation history with context-aware responses
- **Session Management** - Multi-user support with isolated sessions
- **Cron Jobs** - Scheduled tasks and reminders
- **MCP Protocol** - Model Context Protocol for external tool integration

## Installation

```bash
pip install dbot
```

For development:

```bash
git clone https://github.com/yourusername/dbot.git
cd dbot
pip install -e ".[dev]"
```

## Quick Start

### 1. Start the Gateway

```bash
python run.py
```

On first run, this will automatically:
- Create `./config.json` configuration file
- Create `./workspace/` directory

### 2. Configure LLM Provider

Edit `./config.json` to add your API keys:

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

### 3. Configure Feishu Channel

Enable and configure Feishu channel in `./config.json`:

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

The gateway runs on port 18790 by default.

## Supported LLM Providers

- OpenAI (GPT-4, GPT-3.5)
- Anthropic (Claude Opus, Sonnet, Haiku)
- DeepSeek
- Groq
- OpenRouter
- Zhipu AI
- Dashscope (Alibaba)
- Gemini (Google)
- Moonshot
- vLLM (local)
- Ollama (local)

## Supported Channels

| Channel | Description |
|---------|-------------|
| **Feishu/Lark** | WebSocket long connection |

## Built-in Skills

| Skill | Description |
|-------|-------------|
| `github` | Interact with GitHub repositories using `gh` CLI |
| `weather` | Get weather information using wttr.in and Open-Meteo |
| `summarize` | Summarize URLs, files, and YouTube videos |
| `tmux` | Remote-control tmux sessions |
| `clawhub` | Search and install skills from ClawHub registry |
| `skill-creator` | Create new skills |

## Tools

dbot provides a comprehensive tool system:

- **File Tools** - Read, write, edit files in the workspace
- **Web Tools** - Search the web, fetch URL content
- **Shell Tools** - Execute commands (with safety restrictions)
- **Cron Tools** - Schedule and manage recurring tasks
- **Message Tools** - Send cross-platform messages
- **Memory Tools** - Access persistent conversation memory

## Configuration

Configuration is stored in `./config.json`:

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

### Security Options

- `restrict_to_workspace` - Limit file operations to workspace directory
- `blocked_patterns` - Regex patterns for blocked commands
- Channel-specific allowlists for user access control

## Architecture

```
dbot/
├── agent/          # Core agent functionality
│   ├── loop.py     # Main processing engine
│   ├── context.py  # Context building
│   ├── memory.py   # Memory management
│   └── tools/      # Available tools
├── channels/       # Messaging platform integrations
├── providers/      # LLM provider support
├── bus/            # Message queue system
├── config/         # Configuration management
├── skills/         # Extensible skills system
├── templates/      # Template files for AI behavior
├── gateway.py      # Gateway startup logic
└── __main__.py     # Module entry point
```

### Message Bus

The message bus decouples channels from the agent:

1. Channels receive messages and push to the inbound queue
2. The agent loop processes messages from the queue
3. Responses are pushed to the outbound queue
4. Channels send responses back to their platforms

### Templates

Templates in `./workspace/` guide AI behavior:

- `SOUL.md` - Personality and values
- `AGENTS.md` - Agent instructions
- `HEARTBEAT.md` - Periodic tasks
- `MEMORY.md` - Persistent memory
- `USER.md` - User preferences

## Development

### Running Tests

```bash
pytest
```

### Code Style

```bash
ruff check .
ruff format .
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

The skills system is adapted from [OpenClaw](https://github.com/openclaw/openclaw)'s skill system. The skill format and metadata structure follow OpenClaw's conventions to maintain compatibility.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

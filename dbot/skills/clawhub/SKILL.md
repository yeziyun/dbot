---
name: clawhub
description: 从 ClawHub 公共技能注册表搜索和安装代理技能。
homepage: https://clawhub.ai
metadata: {"dbot":{"emoji":"🦞"}}
---

# ClawHub

AI 代理的公共技能注册表。通过自然语言搜索（向量搜索）。

## 何时使用

当用户问以下任何问题时使用此技能：
- "找一个……的技能"
- "搜索技能"
- "安装一个技能"
- "有哪些可用技能？"
- "更新我的技能"

## 搜索

```bash
npx --yes clawhub@latest search "网页抓取" --limit 5
```

## 安装

```bash
npx --yes clawhub@latest install <slug> --workdir ~/.dbot/workspace
```

将 `<slug>` 替换为搜索结果中的技能名称。这会将技能放入 `~/.dbot/workspace/skills/`，dbot 从该位置加载工作区技能。始终包含 `--workdir`。

## 更新

```bash
npx --yes clawhub@latest update --all --workdir ~/.dbot/workspace
```

## 列出已安装

```bash
npx --yes clawhub@latest list --workdir ~/.dbot/workspace
```

## 注意事项

- 需要 Node.js（`npx` 随之安装）。
- 搜索和安装无需 API 密钥。
- 登录（`npx --yes clawhub@latest login`）仅用于发布。
- `--workdir ~/.dbot/workspace` 至关重要 —— 没有它，技能会安装到当前目录而不是 dbot 工作区。
- 安装后，提醒用户开始新会话以加载技能。

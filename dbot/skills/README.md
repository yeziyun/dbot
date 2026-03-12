# dbot 技能

此目录包含扩展 dbot 能力的内置技能。

## 技能格式

每个技能是一个包含 `SKILL.md` 文件的目录，包含：
- YAML 前置配置（name、description、metadata）
- 给代理的 Markdown 指令

## 致谢

这些技能改编自 [OpenClaw](https://github.com/openclaw/openclaw) 的技能系统。
技能格式和元数据结构遵循 OpenClaw 的约定以保持兼容性。

## 可用技能

| 技能 | 描述 |
|------|------|
| `github` | 使用 `gh` CLI 与 GitHub 交互 |
| `weather` | 使用 wttr.in 和 Open-Meteo 获取天气信息 |
| `summarize` | 总结 URL、文件和 YouTube 视频 |
| `tmux` | 远程控制 tmux 会话 |
| `clawhub` | 从 ClawHub 注册表搜索和安装技能 |
| `skill-creator` | 创建新技能 |
| `memory` | 基于 grep 的双层记忆系统 |
| `cron` | 安排提醒和周期性任务 |

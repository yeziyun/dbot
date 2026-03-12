---
name: memory
description: 基于 grep 回忆的双层记忆系统。
always: true
---

# 记忆

## 结构

- `memory/MEMORY.md` — 长期事实（偏好、项目背景、关系）。始终加载到你的上下文中。
- `memory/HISTORY.md` — 仅追加的事件日志。不会加载到上下文中。使用 grep 搜索。每条条目以 [YYYY-MM-DD HH:MM] 开头。

## 搜索过往事件

```bash
grep -i "关键词" memory/HISTORY.md
```

使用 `exec` 工具运行 grep。组合模式：`grep -iE "会议|截止日期" memory/HISTORY.md`

## 何时更新 MEMORY.md

使用 `edit_file` 或 `write_file` 立即写入重要事实：
- 用户偏好（"我喜欢深色模式"）
- 项目背景（"API 使用 OAuth2"）
- 关系（"Alice 是项目负责人"）

## 自动整合

当会话变大时，旧对话会自动摘要并追加到 HISTORY.md。长期事实会被提取到 MEMORY.md。你不需要管理这个过程。

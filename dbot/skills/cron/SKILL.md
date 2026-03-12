---
name: cron
description: 安排提醒和周期性任务。
---

# Cron

使用 `cron` 工具安排提醒或周期性任务。

## 三种模式

1. **提醒** — 消息直接发送给用户
2. **任务** — 消息是任务描述，代理执行并发送结果
3. **一次性** — 在特定时间运行一次，然后自动删除

## 示例

固定提醒：
```
cron(action="add", message="该休息一下了！", every_seconds=1200)
```

动态任务（代理每次执行）：
```
cron(action="add", message="检查 HKUDS/dbot GitHub 星标并报告", every_seconds=600)
```

一次性定时任务（从当前时间计算 ISO 日期时间）：
```
cron(action="add", message="提醒我开会", at="<ISO 日期时间>")
```

带时区的 cron：
```
cron(action="add", message="早会", cron_expr="0 9 * * 1-5", tz="Asia/Shanghai")
```

列出/删除：
```
cron(action="list")
cron(action="remove", job_id="abc123")
```

## 时间表达式

| 用户说 | 参数 |
|--------|------|
| 每 20 分钟 | every_seconds: 1200 |
| 每小时 | every_seconds: 3600 |
| 每天早上 8 点 | cron_expr: "0 8 * * *" |
| 工作日下午 5 点 | cron_expr: "0 17 * * 1-5" |
| 温哥华时间每天早上 9 点 | cron_expr: "0 9 * * *", tz: "America/Vancouver" |
| 在特定时间 | at: ISO 日期时间字符串（从当前时间计算） |

## 时区

使用 `tz` 配合 `cron_expr` 在特定的 IANA 时区安排任务。不带 `tz` 时，使用服务器的本地时区。

---
topics:
  - jsonl 提取
  - 日志清洗
  - 交付产物 URL 还原
product_scope:
  - TeraBox
  - Oreate
data_produces:
  - 末列追加 jsonl URL 的日志表（xlsx/csv）
data_consumes:
  - agent_daily_report / agent_report 日志（xlsx）
  - Oreate 对话日志（csv，含 messageData）
---

# jsonl-extractor 关联声明

工具型 skill：把 TeraBox / Oreate 日志里埋在 JSON 字段中的 jsonl 相对 key 抽出、拼成完整可访问 URL，末列追加输出。

与 [[overseas-agent-analysis]] 强相关：后者的 `build_review_xlsx.py` 内含同样的 `jsonl_url()` 拼接逻辑，本 skill 把这段能力独立成开箱即用工具，供不做全量分析、只想批量捞 URL 的同学直接用。

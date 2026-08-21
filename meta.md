---
topics:
  - jsonl 提取
  - 日志清洗
  - 交付产物 URL 还原
  - 执行轨迹解析
  - 工具调用统计
product_scope:
  - TeraBox
  - Oreate
data_produces:
  - 末列追加 jsonl URL 的日志表（xlsx/csv）
  - 每回合一行的回合索引（含全部身份字段）+ all_urls.txt
  - 工具命中标记表 results.tsv
  - 一行一回合的执行轨迹 NDJSON（含 web_search / web_fetch 结构化明细）
  - 全量量级基线（baseline/，含工具名权威清单）
data_consumes:
  - agent_daily_report / agent_report 日志（xlsx）
  - Oreate 对话日志（csv，含 messageData）
  - agentskill/history 下的 jsonl 执行轨迹文件
---

# jsonl-extractor 关联声明

两层能力的工具型 skill：L1 把 TeraBox / Oreate 日志里埋在 JSON 字段中的 jsonl 相对 key 抽出、拼成完整可访问 URL，末列追加输出；L2 三段流水线全量下载 jsonl，按工具名圈出回合并解析成结构化 NDJSON。

与 [[overseas-agent-analysis]] 强相关：后者的 `build_review_xlsx.py` 内含同样的 `jsonl_url()` 拼接逻辑，本 skill 把这段能力独立成开箱即用工具；L2 产出的 NDJSON 正是后者做 query 行为分析的输入。

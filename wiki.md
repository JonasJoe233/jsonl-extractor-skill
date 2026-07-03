# jsonl-extractor 知识库

## 用途
把 TeraBox / Oreate 日志里埋在 JSON 字段的 jsonl 相对 key 抽出、按产品拼成完整 URL，末列追加输出。工具型 skill，逻辑固定，不做分析。

## 执行索引
| 日期 | 产品 | 输入 | 总行/命中 | 备注 |
|------|------|------|-----------|------|
| 2026-07-03 | terabox | agent_daily_report_2026-06-26 | 44,011 / 43,946（99.9%） | 建 skill 时全量验证，URL 拼接正确 |

## 沉淀
- TeraBox 全量 assistant 主导的日志命中率约 99%+；混大量 user 行/抽样文件会显著偏低，属正常。
- 两产品 URL 规则差异是唯一易错点：TeraBox 下划线保留原样拼，Oreate 两段 hash 间下划线转斜杠。逻辑与 [[overseas-agent-analysis]] 的 `build_review_xlsx.py::jsonl_url()` 一致。

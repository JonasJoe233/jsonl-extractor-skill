# jsonl-extractor 知识库

## 用途
把 TeraBox / Oreate 日志里埋在 JSON 字段的 jsonl 相对 key 抽出、按产品拼成完整 URL，末列追加输出。工具型 skill，逻辑固定，不做分析。

## 执行索引
| 日期 | 产品 | 输入 | 总行/命中 | 备注 |
|------|------|------|-----------|------|
| 2026-07-03 | terabox | agent_daily_report_2026-06-26 | 44,011 / 43,946（99.9%） | 建 skill 时全量验证，URL 拼接正确 |
| 2026-08-21 | oreate | 08-01~08-10 全量 CSV | 750,503 回合 / jsonl 零失败 | L2 三段流水线上线，产出 `baseline/`；SKILL.md 升为两层能力 |
| 2026-08-21 | oreate | 08-01 CSV 前 3000 行（独立复验） | 1,424 回合 / 400 url 扫 / 26 回合解析 | 三段全跑通：16 身份字段齐全、search 分支出 query/gl/hl/results[]、通用分支出 calls[]；补上 stage2 工具指纹守卫 |

## 沉淀
- TeraBox 全量 assistant 主导的日志命中率约 99%+；混大量 user 行/抽样文件会显著偏低，属正常。
- 两产品 URL 规则差异是唯一易错点：TeraBox 下划线保留原样拼，Oreate 两段 hash 间下划线转斜杠。逻辑与 [[overseas-agent-analysis]] 的 `build_review_xlsx.py::jsonl_url()` 一致。
- L2 的铁律是全字段保留：回溯常要看 vip_type 这类身份信息，jsonl 层已经没有这些字段，裁掉就得回去重新 join。加字段改 `stage1_index.py` 的 `COLS`，不在后续阶段做投影。
- 工具名从 `baseline/README.md` 的 16 个清单里挑，不要猜拼写。**日志里没有叫 deep research 的 plugin**，`source_name` 只有 `htmlPPT` 和空值两种——要圈 deep research 的回合得先定识别口径。
- 沙箱单次 bash 有墙钟上限、后台进程会被杀，stage2/stage3 必须靠 `--deadline` 分批续跑，不要写 nohup。企业代理是 MITM 证书，`verify=False` 是必须的。
- stage2 续跑只按 url 去重，**换 `--tools` 沿用旧 results.tsv 会静默空转**（`[resume] 剩余 0`，新工具命中全 0，看着像成功）。已加 `results.tsv.tools` 指纹守卫拦住这种情况，旧的无指纹文件只 warn，仍需自己判断。
- `~/.claude/skills` 是受保护路径：从 Downloads 拷文件进来会 `Operation not permitted`，需关沙箱执行，且 `cp -R` 会因扩展属性/`.cc-writes` 失败，改用 `cp -X` 逐文件拷。

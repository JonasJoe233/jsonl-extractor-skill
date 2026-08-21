---
name: jsonl-extractor
description: 清洗 TeraBox / Oreate 的 Agent 日志。两层能力：① 在原表末尾加一列 jsonl 完整 URL（回放用户行为的必要链接）；② 下载 jsonl 深挖执行轨迹，按工具名（web_search_tool / web_fetch_tool 等）圈出回合并解析成结构化 NDJSON。触发词：清洗日志、提取 jsonl、加一列 jsonl、回放用户行为、复盘这轮对话、replay、扫一下调用了 XX 工具的日志、webfetch 数据、搜索数据。
tags:
  - jsonl-extractor
---

## 目录文件说明

| 文件/目录 | 作用 |
|-----------|------|
| [[jsonl-extractor/SKILL]] | **Agent 执行入口**（唯一权威）：两层能力判定、命令、决策点、成功判定 |
| [[jsonl-extractor/scripts/extract_jsonl.py\|scripts/extract_jsonl.py]] | L1 主脚本：读 xlsx/csv → 逐行抽 jsonl key → 按产品拼 URL → 末列追加输出 |
| [[jsonl-extractor/scripts/stage1_index.py\|scripts/stage1_index.py]] | L2 stage1：源 CSV → 每回合一行的索引（保留全部身份字段）+ all_urls.txt |
| [[jsonl-extractor/scripts/stage2_scan.py\|scripts/stage2_scan.py]] | L2 stage2：全量流式扫，字节匹配标记每回合命中了哪些工具，支持续跑 |
| [[jsonl-extractor/scripts/stage3_extract.py\|scripts/stage3_extract.py]] | L2 stage3：命中回合二次抓取，解析成一行一回合的 NDJSON |
| [[jsonl-extractor/baseline/README\|baseline/README.md]] | 基线速查（人 + agent 读）：工具名权威清单、按天量级、实测吞吐 |
| [[jsonl-extractor/baseline/baseline_2026-08-01_08-10.json\|baseline/baseline_2026-08-01_08-10.json]] | 同一基线的机器可读版，供脚本/对比直接读取 |
| [[jsonl-extractor/README]] | 面向**人**的速查（非 agent 的同学手动跑）。**Agent 忽略此文件**，一切以 SKILL.md 为准 |
| [[jsonl-extractor/meta]] | 关联声明（topics/product_scope/data），供 `_discover.py` 计算关联 |
| [[jsonl-extractor/wiki]] | 执行索引与跨次沉淀 |
| `SKILL.md.bak` | 升级前的 L1-only 版本备份，新版验证无误后可删 |
| `raw/` | 批处理留痕（工具型 skill 通常为空） |
| [[jsonl-extractor/scripts/stage2_scan]] | (待补充用途说明) |

---

# TeraBox / Oreate 日志 jsonl 提取与深挖

两层能力，先判断用户要哪一层。

**L1 只要链接**：在原表最后新增一列 `jsonl`，填该行交付产物 jsonl 的完整可访问 URL，其余列一字不动。用户拿链接去策略回放系统还原行为。关键词：清洗一下、提取 jsonl、加一列、转成能点开的链接、回放、复盘这个 case。

**L2 要日志里面的东西**：把 jsonl 全量下载下来，按工具名圈出回合，解析成一行一回合的 NDJSON，再做分析。关键词：调用了 XX 工具的日志、webfetch 的数据、搜索了什么、看看它执行了几步、这批 query 都在干什么、统计工具调用。

判断依据一句话：**要的是「能点开的链接」还是「链接里面的内容」。** 拿不准就问一句。

## L1：加一列 jsonl URL

**唯一命令**（路径相对本 SKILL.md 所在目录）：

```bash
python3 scripts/extract_jsonl.py <日志文件> --product <terabox|oreate>
```

**🛑 唯一决策点 —— 产品必须确认，禁止自己猜：** `--product` 决定 URL 前缀与下划线规则，选错则整列 URL 全部 404。用户没明确说是哪个产品时停下来问：「这是 TeraBox 还是 Oreate 的日志？两者 URL 拼法不同。」不要凭文件名或列名推断。

| 产品 | 前缀 | 下划线处理 |
|------|------|-----------|
| TeraBox | `https://storage.googleapis.com/tera-server-manager/` | 保留，原始 key 原样拼 |
| Oreate | `https://cdn.oreateai.com/` | 两段 hash 间的 `_` 转成 `/` |

**成功判定**（跑完自检，全满足才算交付）：退出码 0；控制台打印「提取到 jsonl: N（X%）」且 X% 合理（TeraBox 全量约 99%+，含大量 user 行或抽样文件会偏低）；输出文件列数 = 原列数 + 1，末列名为 `jsonl`。**X% = 0 就是产品选错或文件不是 Agent 日志，报告用户、不要交付。**

**产物**：默认统一输出 `.xlsx`（CSV 输入也转 xlsx）。想要 CSV 显式 `-o xxx.csv`——写哪种格式看输出后缀，不看输入。

全部参数：`--product/-p`（必填）、`-o/--out`、`--colname`（默认 `jsonl`）、`--column`（`url` 默认 / `key` 只要相对路径）。

**原理**：jsonl 的相对 key 不在独立列里，埋在 assistant 行某个单元格的 JSON 里，字段名 `object`，形如 `agentskill/history/{hash1}_{hash2}.jsonl`（hash1 = encoded chat_id）。脚本逐行扫所有单元格正则抓，不写死列名，所以 TeraBox 39 列 schema 和 Oreate CSV 都覆盖。

## L2：下载 jsonl，按工具挖执行轨迹

三段流水线，每段都能断点续跑。**先读 `baseline/README.md`**——工具名清单、历史量级、实测吞吐都在里面，能省掉一轮试错。

```bash
export http_proxy=http://agent.baidu.com:8891 https_proxy=http://agent.baidu.com:8891

# stage1  CSV → 每回合一行的索引（保留全部身份/上下文字段）+ all_urls.txt
python3 scripts/stage1_index.py --src <CSV目录> --out <工作目录>

# stage2  全量流式扫，标记每个回合命中了哪些工具（只做字节匹配，不解析 JSON，很快）
python3 scripts/stage2_scan.py <工作目录>/all_urls.txt <工作目录>/results.tsv \
    --tools web_search_tool,web_fetch_tool --workers 48 --deadline 150
#   反复调用直到 [resume] 显示剩余 0

# stage3  命中回合二次抓取，解析成一行一回合的 NDJSON
python3 scripts/stage3_extract.py --index <工作目录> --results <工作目录>/results.tsv \
    --out <工作目录>/turns.ndjson --tool web_search_tool \
    --keep web_search_tool,web_fetch_tool --workers 40 --deadline 150
```

`--tool` 选哪些回合抓（任一命中即抓），`--keep` 选哪些工具展开成结构化明细，其余工具只在 `tool_calls` 里留调用次数。web_search_tool 和 web_fetch_tool 有专门的解析分支（搜索出 query/gl/hl/results[]，抓取出 target/args/out_len）；别的工具走通用分支，落在 `calls[]` 里带 args、meta、输出头部 800 字符。

**⚠ 换工具必须换 results.tsv 文件名。** stage2 的续跑靠「url 是否已在 results.tsv 出现」判断，不看当初扫的是哪些工具。所以同一个 results.tsv 换 `--tools` 再跑，会打印 `[resume] 剩余 0` 直接空转退出——看着像成功，实际一条没扫，新工具的命中全是 0。要扫新工具就写新文件：`results_ppt.tsv`、`results_memory.tsv`。一次把要扫的工具都列进 `--tools` 最省事，字节匹配加几个关键词几乎不增加耗时。

### 铁律：全字段保留，一行自证

NDJSON 每一行都必须自带该回合的全部上下文字段——`url`（可回放）、`log_date`、`chat_id`、`message_id`、`user_id`、`email`、`vip_type`、`platform`、`source_name`、`send_time`、`turnLen`、`interrupt_reason`、`artifact_num`、`rating_1`、`query_text`、`artifact_infos`。

理由是用户明确提过的：回溯的时候经常要看用户 VIP 身份这类信息，如果清洗时裁掉了，就得回去重新 join，而 jsonl 那一层已经没有这些字段了。所以宁可冗余也不裁剪。想加字段就改 `stage1_index.py` 的 `COLS`，不要在后面的阶段做投影。

分析脚本也遵守同一条：`rec.update(...)` 只追加不覆盖，规则版判定要另存一列（比如 `scenario_rule`），别把原判定冲掉。

### 沙箱与网络的坑

单次 bash 调用有墙钟上限，后台进程会随调用结束被杀，所以 stage2/stage3 必须用 `--deadline` 分批、靠续跑推进，不要写 `nohup` 指望它自己跑完。企业代理是 MITM 证书，脚本里 `verify=False` 是必须的，不是偷懒。

## 从 NDJSON 到分析结论

如果用户要的不只是数据而是判断，往下这几步是上次跑通的路径，可以照搬：

域名分级（目标源同类 / 学术出版商 / 官方政府 / 聚合百科 / 低质 UGC / 其他）→ 关键词规则先打一版标签 → **分层抽样送盲标** → 用标注训 TF-IDF（词 1-2gram + char_wb 3-5gram）+ 逻辑回归，`sample_weight = N层 / n层内标注数`，这样精确率召回率是总体口径 → 主动学习补第二轮（不确定样本 + 少数类 + 纯随机切片，纯随机那部分单独留作无偏检验集）→ 全量预测。

上次纯关键词规则的精确率只有 24%~43%，不能交付；换成上面这套是 macro F1 66.1%。**别在正则上反复调，直接上监督模型。**

分析报告口径的两条硬要求：量级同时给「模型判定」和「人工标注加权校准后」两个数，差值就是模型偏差方向；每类指标带 95% 置信半宽，区间宽的类别（标注量小的）只当存在性证据，不做资源测算。

**盲标的坑**：用 subagent 批量标注时，如果它在回复正文里逐条列推理，会撞 32000 output token 上限直接失败。prompt 里必须写明「不要在回复或思考输出里写任何逐条分析、清单或推理过程，直接写文件」，单批控制在 130 条以内。另外给 subagent 指定 `model: sonnet` 会 503（当前分组无该渠道），用继承模型。

## 基线：2026-08-01 至 08-10

`baseline/` 下维护着这十天 75.0 万个回合的全量基线，机器可读版在 `baseline_2026-08-01_08-10.json`，速查在 `baseline/README.md`。

**用户不给新日志时，直接引用它回答量级问题；给了新日志，跑完拿它对比判断哪条是真变化。** 引用必须带一句「这是 2026-08-01~08-10 的基线」，不要说成当前值。

高频要用的几个数：全量 750,503 个 assistant 回合，jsonl 下载零失败；web_search_tool 命中 35,631 回合（4.75%），web_fetch_tool 命中 26,234 回合（3.50%）；搜索命中回合内 162,970 次搜索、1,265,573 条返回链接、空结果率 5.9%、209,077 个唯一域名；返回最多的域名是 facebook / youtube / instagram / researchgate / tiktok；hl 里 es 56,493 比 en 48,112 多，需求主力在拉美。08-04 源 CSV 未导出，看趋势跳过这天。

工具名清单也在基线里（16 个，从 web_search_tool 到 memory_write）。**要扫别的工具就从那份清单挑名字，别自己猜拼写。** 特别注意：日志里没有任何叫 deep research 的 plugin，`source_name` 只有 `htmlPPT` 和空值两种，所以要圈 deep research 的回合得先确认靠什么字段识别，不能默认一扫就有。

## 已知边界

xlsx 直解 XML：TeraBox 导出工具把 `<dimension>` 写成 `A1`，openpyxl/pandas 会误读成只有 1 行，L1 脚本复用了直解 worksheet XML 的读法绕过它。

CSV 超大单格：Oreate 的 `messageData` 单格可能极大，脚本已把 `csv.field_size_limit` 拉满。

Excel 单格上限：写 xlsx 时清掉非法控制字符并截断到 32767 字符。

占比不是 100% 是正常的：user 行、被取消的回合、无 skill 交付的回合本就没有 jsonl。

jsonl 帧格式：外层 JSON 的 `result` 是字符串化的内层 JSON，要二次 `loads`；只有 `plugin_call` / `plugin_call_output` 且 `status=completed`、非 delta 的帧可用；`web_search_tool` 的 `data.output` 是双层字符串化的结果数组。

## 归档

工具型 skill，本目录不产出分析归档。跑完一批分析后，把新的量级数字并进 `baseline/`（新增一个日期段文件，不要覆盖旧基线），并在 `wiki.md` 记一行执行索引。

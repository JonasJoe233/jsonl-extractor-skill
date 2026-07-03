---
name: jsonl-extractor
description: |
  清洗 TeraBox / Oreate 的 Agent 日志，在原表最后新增一列 jsonl，写出交付产物 jsonl 文件的完整可访问 URL。jsonl 是策略回放用户行为的必要链接——想回放某轮对话、看用户具体做了什么，都要先拿到这条 URL。开箱即用：任意 agent 读 SKILL.md 的「执行契约」一节即可跑对，无需读脚本源码。
  触发词：清洗日志、提取 jsonl、加一列 jsonl、日志转 URL、jsonl 链接、回放、回放用户行为、看用户行为、复盘这轮对话、extract jsonl、clean log、replay。
  确定性触发（直接执行）：用户给一份 TeraBox/Oreate 日志（xlsx/csv）说提取 jsonl / 加 jsonl 列 / 想回放用户行为 / 想看用户在某轮做了什么。
  非确定性触发（先问）：给了日志但没说产品——询问："这是 TeraBox 还是 Oreate 的日志？（URL 拼法不同）"
tags:
  - jsonl-extractor
---

## 目录文件说明

| 文件/目录 | 作用 |
|-----------|------|
| [[jsonl-extractor/SKILL]] | **Agent 执行入口**（唯一权威）：触发条件、命令、决策点、成功判定 |
| [[jsonl-extractor/scripts/extract_jsonl.py\|scripts/extract_jsonl.py]] | 主脚本：读 xlsx/csv → 逐行抽 jsonl key → 按产品拼 URL → 末列追加输出 |
| [[jsonl-extractor/README]] | 面向**人**的速查（非 agent 的同学手动跑）。**Agent 忽略此文件**，一切以 SKILL.md 为准 |
| [[jsonl-extractor/meta]] | 关联声明（topics/product_scope/data），供 `_discover.py` 计算关联 |
| [[jsonl-extractor/wiki]] | 执行索引与跨次沉淀 |
| [[jsonl-extractor/scripts/extract_jsonl]] | (待补充用途说明) |

---

# TeraBox / Oreate 日志 jsonl 提取

给一份 Agent 对话日志，在原表**最后新增一列 `jsonl`**，填该行交付产物 jsonl 文件的完整可访问 URL，其余列一字不动。

## 为什么要捞 jsonl（理解用户 Query 用）

**jsonl 是策略回放用户行为的必要链接。** 日志表里只有 query 文本和结果字段，看不到这一轮对话里 Agent 具体怎么一步步执行的；那条完整的执行轨迹存在 jsonl 文件里，拿到它的 URL 才能回放。

所以当用户说这类话时，**本质诉求就是本 skill**，即使没提"jsonl"三个字：

- "帮我回放一下 / 回放这轮对话 / replay"
- "我想看看用户（在这条 query 里）做了什么 / 用户行为"
- "复盘一下这几条 / 这个 case 怎么回事"

识别到这类意图 → 确认是哪个产品的日志 → 跑本 skill 提取 jsonl URL 交付，用户拿链接去策略回放系统还原行为。

---

## ⚡ Agent 执行契约（读这一节即可跑对，无需读脚本源码）

**路径约定**：下方命令里的 `scripts/extract_jsonl.py` 是**相对本 SKILL.md 所在目录**的路径。执行前先 `cd` 到本 skill 目录，或把 `scripts/...` 换成该目录的实际路径。不同机器/不同用户的绝对路径不同，勿写死。

**唯一命令**：

```bash
python3 scripts/extract_jsonl.py <日志文件> --product <terabox|oreate>
```

**🛑 唯一决策点 —— 产品必须确认，禁止自己猜：**
`--product` 决定 URL 前缀与下划线规则，**terabox 和 oreate 拼法不同，选错则整列 URL 全部 404**。
用户没明确说是哪个产品时，**停下来问**：「这是 TeraBox 还是 Oreate 的日志？两者 URL 拼法不同。」不要凭文件名或列名推断。

**成功判定（跑完自检，全满足才算交付）：**
1. 退出码 0，控制台打印了「提取到 jsonl: N（X%）」。
2. 命中率 X% 合理：TeraBox 全量日志约 **99%+**；含大量 user 行/抽样文件会偏低，属正常。**若 X% = 0**，多半是产品选错或文件不是 Agent 日志——报告用户、不要交付。
3. 输出文件存在，列数 = 原列数 + 1，末列名为 `jsonl`。

**产物**：默认原名加 `_jsonl` 后缀、同格式（`日志.xlsx` → `日志_jsonl.xlsx`），只在末尾多一列，其余列不动。

## 触发条件

- 用户给一份 TeraBox / Oreate 日志（.xlsx 或 .csv），说"清洗一下""提取 jsonl""加一列 jsonl""转成能点开的链接"
- 用户问"这些日志里的 jsonl 怎么捞出来"

## 一句话原理（背景，非执行必读）

jsonl 的相对 key **不在独立列里**，而是埋在 assistant 行某个单元格的 JSON 里，字段名叫 `object`，形如 `agentskill/history/{hash1}_{hash2}.jsonl`（hash1 = encoded chat_id）。日志里**只有相对 key、没有域名**，脚本负责两件事：

1. **抽 key**：逐行扫所有单元格，正则抓 `"object":"...jsonl"`（抓不到再兜底抓裸路径 `agentskill/history/*.jsonl`）。不写死列名，所以 TeraBox 39 列 schema 和 Oreate CSV 都能覆盖。
2. **拼 URL**：按产品拼前缀，**两个产品规则不同，拼错会 404**：

| 产品 | 前缀 | 下划线处理 |
|------|------|-----------|
| **TeraBox** | `https://storage.googleapis.com/tera-server-manager/` | **保留**，原始 key 原样拼 |
| **Oreate** | `https://cdn.oreateai.com/` | 两段 hash 间的 `_` **转成 `/`** |

## 全部参数（默认值已够用，一般无需调）

```bash
# 指定输出路径
python3 scripts/extract_jsonl.py <日志> -p oreate -o 输出.xlsx

# 只要相对路径、不要完整 URL
python3 scripts/extract_jsonl.py <日志> -p terabox --column key
```

| 参数 | 说明 |
|------|------|
| `infile` | 输入日志，`.xlsx` 或 `.csv`（位置参数，必填） |
| `--product` / `-p` | `terabox` 或 `oreate`，**必填**，决定 URL 前缀与下划线规则 |
| `-o` / `--out` | 输出路径，默认原名加 `_jsonl` 后缀、格式与输入一致 |
| `--colname` | 新增列名，默认 `jsonl` |
| `--column` | `url`（默认，完整可点链接）或 `key`（只要相对路径） |

## 已知边界与坑

- **xlsx 直解 XML**：TeraBox 导出工具把 `<dimension>` 写成 `A1`，openpyxl/pandas 会误读成只有 1 行，脚本复用了直解 worksheet XML 的读法绕过它。
- **CSV 超大单格**：Oreate 的 `messageData` 单格可能极大，脚本已把 `csv.field_size_limit` 拉满。
- **Excel 单格上限**：写 xlsx 时清掉非法控制字符并截断到 32767 字符（Excel 硬上限），避免写坏文件；已核对 TeraBox 39 列均不超限。
- **占比不是 100% 是正常的**：user 行、被取消的回合、无 skill 交付的回合本就没有 jsonl，对应行 `jsonl` 列留空。
- **依赖**：`openpyxl`（仅写 xlsx 时用）。读 xlsx 靠标准库 zipfile，无额外依赖。

## 归档

作为工具型 skill，本目录不产出分析归档；若某次批处理需要留痕，在 `raw/YYYY-MM-DD/` 放 input.md + summary.md 即可。

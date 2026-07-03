# jsonl-extractor · 开箱即用速查

给一份 **TeraBox / Oreate 的 Agent 日志**，在原表最后加一列 `jsonl`，填每行交付产物 jsonl 文件的**完整可点 URL**。其余列一字不动。

## 一行命令

```bash
# TeraBox 日志
python3 scripts/extract_jsonl.py 你的日志.xlsx --product terabox

# Oreate 日志
python3 scripts/extract_jsonl.py 你的日志.csv --product oreate
```

跑完在原文件同目录生成 `你的日志_jsonl.xlsx`，末列就是链接，直接点开。**CSV 输入也默认转成 xlsx**；想要 CSV 输出就显式 `-o xxx.csv`。

## 参数

| 参数 | 必填 | 说明 |
|------|:----:|------|
| `infile` | ✅ | 输入日志，`.xlsx` 或 `.csv` |
| `--product` / `-p` | ✅ | `terabox` 或 `oreate`。**必填，两个产品 URL 拼法不同，选错会 404** |
| `-o` / `--out` | | 输出路径，默认 `原名_jsonl.xlsx`（CSV 输入也转 xlsx）；要 CSV 输出就 `-o xxx.csv` |
| `--colname` | | 新列名，默认 `jsonl` |
| `--column` | | `url`（默认，完整链接）/ `key`（只要相对路径） |

## 依赖

- Python 3
- `openpyxl`（只有输出 xlsx 时才用到）：`pip3 install openpyxl`
- 读 xlsx / 读写 csv 都是标准库，无需额外安装

## 常见问题

**Q：为什么命中率不是 100%？**
正常。user 提问行、被取消的回合、没触发 skill 的回合本来就没有 jsonl 产物，这些行 `jsonl` 列留空。TeraBox 全量日志通常 99%+。

**Q：能一次处理多个文件吗？**
当前一次一个文件。多个文件写个循环即可：
```bash
for f in *.xlsx; do python3 scripts/extract_jsonl.py "$f" -p terabox; done
```

**Q：URL 打不开 / 404？**
先确认 `--product` 选对了——TeraBox 和 Oreate 的域名和下划线规则不一样，用错产品拼出来的链接必然打不开。

**Q：Excel 打开报错文件损坏？**
脚本已自动清理非法控制字符并把超长单元格截断到 Excel 上限（32767 字符），正常不会遇到。若仍异常，用 `--column key` 只输出相对路径规避。

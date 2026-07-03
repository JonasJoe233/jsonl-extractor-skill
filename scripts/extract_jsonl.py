#!/usr/bin/env python3
"""
出海 Agent 日志 jsonl 提取器（TeraBox / Oreate 通用，开箱即用）。

做一件事：读入一份日志（.xlsx 或 .csv），在原表最后新增一列 jsonl，
写出交付产物 jsonl 的完整可访问 URL，其余列原样保留。

为什么不写死列名：TeraBox 的 jsonl key 埋在 data 列的 "object" 字段里，
但不同产品/不同导出模板列名不一定一致，所以本脚本逐行扫所有单元格，
用正则抓 "object":"...jsonl"（抓不到再兜底抓 agentskill/history/*.jsonl），
不依赖固定列位置——TeraBox / Oreate 都能覆盖。

URL 拼法两个产品不同，必须用 --product 指定，拼错会 404：
  TeraBox: https://storage.googleapis.com/tera-server-manager/{key}   下划线保留、原样拼
  Oreate : https://cdn.oreateai.com/agentskill/history/{h1}/{h2}.jsonl 两段 hash 间下划线转斜杠

用法:
    python3 extract_jsonl.py 日志.xlsx --product terabox
    python3 extract_jsonl.py 日志.csv  --product oreate  -o 输出.xlsx
    python3 extract_jsonl.py 日志.xlsx --product terabox --column key   # 只要相对路径
"""
import sys, os, re, html, csv, zipfile, argparse

# ---------- jsonl key 提取 ----------
OBJ_RE = re.compile(r'"object"\s*:\s*"([^"]+\.jsonl)"')
FALLBACK_RE = re.compile(r'(agentskill/history/[0-9A-Za-z_]+\.jsonl)')

def extract_key(row_cells):
    """从一行的所有单元格里找出 jsonl 相对 key；优先 object 字段，兜底路径正则。"""
    for cell in row_cells:
        if cell and '.jsonl' in cell:
            m = OBJ_RE.search(cell)
            if m:
                return m.group(1).lstrip('/')
    for cell in row_cells:
        if cell and '.jsonl' in cell:
            m = FALLBACK_RE.search(cell)
            if m:
                return m.group(1).lstrip('/')
    return ""

# ---------- URL 拼接（两产品规则不同）----------
TERABOX_PREFIX = "https://storage.googleapis.com/tera-server-manager/"
OREATE_PREFIX = "https://cdn.oreateai.com/"
OREATE_KEY_RE = re.compile(r'(agentskill/history/)([0-9a-fA-F]+)_([0-9a-fA-F]+\.jsonl)$')

def to_url(key, product):
    if not key:
        return ""
    if product == "oreate":
        m = OREATE_KEY_RE.match(key)
        if m:  # 两段 hash 之间的下划线转斜杠
            return f"{OREATE_PREFIX}{m.group(1)}{m.group(2)}/{m.group(3)}"
        return OREATE_PREFIX + key
    return TERABOX_PREFIX + key  # TeraBox：原样拼，下划线保留

# ---------- 读 xlsx（直解 XML，绕过导出工具的 <dimension ref="A1"> bug）----------
def read_xlsx(fn):
    z = zipfile.ZipFile(fn)
    shared = []
    try:
        d = z.read('xl/sharedStrings.xml').decode('utf-8', 'ignore')
        for si in re.findall(r'<si>(.*?)</si>', d, re.S):
            shared.append(html.unescape(''.join(re.findall(r'<t[^>]*>(.*?)</t>', si, re.S))))
    except KeyError:
        pass
    names = [n for n in z.namelist() if re.match(r'xl/worksheets/sheet\d+\.xml$', n)]
    names.sort()
    data = z.read(names[0]).decode('utf-8', 'ignore')
    z.close()

    def colnum(ref):
        s = re.match(r'([A-Z]+)', ref).group(1); n = 0
        for ch in s:
            n = n * 26 + (ord(ch) - 64)
        return n - 1

    def cv(cm):
        t = re.search(r't="([^"]+)"', cm); tv = t.group(1) if t else None
        il = re.search(r'<is>.*?<t[^>]*>(.*?)</t>', cm, re.S)
        if il:
            return html.unescape(il.group(1))
        vm = re.search(r'<v>(.*?)</v>', cm, re.S)
        if vm is None:
            return ''
        v = vm.group(1)
        return shared[int(v)] if tv == 's' else html.unescape(v)

    out = []
    for r in re.findall(r'<row[ >].*?</row>', data, re.S):
        rd = {}; mx = -1
        for cm in re.findall(r'<c\b[^>]*?(?:/>|>.*?</c>)', r, re.S):
            ref = re.search(r'r="([A-Z]+\d+)"', cm); ci = colnum(ref.group(1)) if ref else 0
            rd[ci] = cv(cm); mx = max(mx, ci)
        out.append([rd.get(i, '') for i in range(mx + 1)])
    return out

def read_csv(fn):
    csv.field_size_limit(sys.maxsize)  # messageData 单格可能极大
    with open(fn, encoding='utf-8-sig', newline='') as fh:
        return [row for row in csv.reader(fh)]

# ---------- 写 xlsx（清非法控制字符 + 截断到 Excel 单格上限）----------
ILLEGAL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')
def clean(v):
    v = ILLEGAL.sub('', str(v))
    return v[:32767]

def write_xlsx(rows, out):
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active
    for r in rows:
        ws.append([clean(x) for x in r])
    ws.freeze_panes = 'A2'
    wb.save(out)

def write_csv(rows, out):
    with open(out, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh)
        for r in rows:
            w.writerow(r)

# ---------- 主流程 ----------
def main():
    ap = argparse.ArgumentParser(description="给 TeraBox/Oreate 日志新增一列 jsonl URL")
    ap.add_argument("infile", help="输入日志 .xlsx 或 .csv")
    ap.add_argument("--product", "-p", required=True, choices=["terabox", "oreate"],
                    help="决定 URL 前缀与下划线规则，必填")
    ap.add_argument("-o", "--out", help="输出路径，默认原名加 _jsonl 后缀，同格式")
    ap.add_argument("--colname", default="jsonl", help="新增列名，默认 jsonl")
    ap.add_argument("--column", choices=["url", "key"], default="url",
                    help="url=完整可点链接(默认)；key=只要相对路径")
    args = ap.parse_args()

    fn = args.infile
    if not os.path.exists(fn):
        sys.exit(f"找不到文件：{fn}")
    ext = os.path.splitext(fn)[1].lower()
    if ext not in (".xlsx", ".csv"):
        sys.exit(f"只支持 .xlsx / .csv，收到：{ext}")

    rows = read_xlsx(fn) if ext == ".xlsx" else read_csv(fn)
    if not rows:
        sys.exit("空文件")

    header = rows[0]
    ncol = len(header)
    out_rows = [header + [args.colname]]
    n_hit = 0
    for r in rows[1:]:
        cells = r + [''] * (ncol - len(r)) if len(r) < ncol else r
        key = extract_key(cells)
        if key:
            n_hit += 1
        val = key if args.column == "key" else to_url(key, args.product)
        out_rows.append(cells + [val])

    # 默认输出统一为 .xlsx（含 CSV 输入也转 xlsx）；写哪种格式看【输出】后缀，不看输入
    out = args.out or f"{os.path.splitext(fn)[0]}_jsonl.xlsx"
    out_ext = os.path.splitext(out)[1].lower()
    if out_ext == ".csv":
        write_csv(out_rows, out)
    else:
        write_xlsx(out_rows, out)

    total = len(rows) - 1
    print(f"产品        : {args.product}")
    print(f"总数据行    : {total:,}")
    if total:
        print(f"提取到 jsonl: {n_hit:,}（{n_hit/total*100:.1f}%）")
    print(f"输出列      : {args.colname}（{args.column}）")
    print(f"已写出      : {out}")

if __name__ == "__main__":
    main()

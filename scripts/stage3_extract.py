#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stage3：对命中的回合二次抓取 jsonl，解析成一行一回合的 NDJSON。

设计原则：**每行自带回合的全部上下文字段**（user_id / email / vip_type / platform /
source_name / interrupt_reason / rating_1 / artifact_num / query_text / jsonl url ...），
任何一行单独拿出来都能溯源和回放，后续分析不需要再 join 回原表。

用法：
  python3 stage3_extract.py --index <索引目录> --results results.tsv --out turns.ndjson \\
      [--tool web_search_tool] [--keep web_search_tool,web_fetch_tool] \\
      [--workers 40] [--deadline 150] [--proxy URL]

  --tool  选哪些回合：results.tsv 的命中列里含该 tool 才抓（多个用逗号，任一命中即抓）
  --keep  抓下来后哪些 tool 展开成结构化明细，其余 tool 只在 tool_calls 里留次数

产物 NDJSON 字段：上下文字段 + tool_calls{name:次数} + n_search / n_fetch /
searches[] / fetches[] / calls[]（--keep 里非搜索抓取类工具的调用明细）。
断点续跑：已在 out 里出现过的 url 自动跳过。
"""
import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests
import urllib3

urllib3.disable_warnings()


def extract_results(output):
    """web_search 的 output 是双层字符串化：'[{"type":"text","text":"[{title,link,...}]"}]'"""
    if not isinstance(output, str):
        return []
    try:
        blocks = json.loads(output)
    except Exception:
        return []
    if isinstance(blocks, dict):
        blocks = [blocks]
    items = []
    for b in blocks if isinstance(blocks, list) else []:
        txt = b.get("text") if isinstance(b, dict) else None
        if not txt:
            continue
        try:
            arr = json.loads(txt)
        except Exception:
            continue
        if isinstance(arr, dict):
            arr = [arr]
        for it in arr if isinstance(arr, list) else []:
            if isinstance(it, dict):
                items.append({"title": (it.get("title") or "")[:300],
                              "link": (it.get("link") or it.get("url") or "")[:500],
                              "snippet": (it.get("snippet") or "")[:500],
                              "date": it.get("date", ""), "position": it.get("position")})
    return items


def parse_jsonl(raw, keep):
    """只认非 delta 且 status=completed 的 plugin_call / plugin_call_output 帧。
    外层 JSON 的 result 是字符串化的内层 JSON，要二次 loads。"""
    searches, fetches, calls, tools = [], [], [], {}
    pending = {}
    for line in raw.splitlines():
        if '"result"' not in line:
            continue
        try:
            outer = json.loads(line)
            r = outer.get("result")
            d = json.loads(r) if isinstance(r, str) else None
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        t, st, delta = d.get("type"), d.get("status"), d.get("delta")
        data = d.get("data") or {}
        if t == "plugin_call" and st == "completed" and not delta:
            name = data.get("name") or ""
            if name:
                tools[name] = tools.get(name, 0) + 1
            try:
                args = json.loads(data.get("arguments") or "")
            except Exception:
                args = {"_raw": (data.get("arguments") or "")[:500]}
            pending[data.get("call_id") or ""] = (name, args)
        elif t == "plugin_call_output" and st == "completed" and not delta:
            name = data.get("name") or ""
            cid = data.get("call_id") or ""
            meta = data.get("metadata") or {}
            cname, cargs = pending.get(cid, (name, {}))
            out = data.get("output")
            if name not in keep:
                continue
            if name == "web_search_tool":
                res = extract_results(out)
                searches.append({"call_id": cid,
                                 "query": cargs.get("query") or meta.get("query") or "",
                                 "gl": cargs.get("gl", ""), "hl": cargs.get("hl", ""),
                                 "result_count": meta.get("count", len(res)), "results": res})
            elif name == "web_fetch_tool":
                fetches.append({"call_id": cid,
                                "target": cargs.get("url") or cargs.get("urls") or meta.get("url", ""),
                                "args": {k: v for k, v in cargs.items() if k != "_raw"},
                                "out_len": len(out) if isinstance(out, str) else None,
                                "out_head": out[:800] if isinstance(out, str) else None})
            else:
                calls.append({"call_id": cid, "name": name,
                              "args": {k: str(v)[:400] for k, v in cargs.items()},
                              "meta": {k: str(v)[:200] for k, v in meta.items()},
                              "out_len": len(out) if isinstance(out, str) else None,
                              "out_head": out[:800] if isinstance(out, str) else None})
    return searches, fetches, calls, tools


class Fetcher:
    def __init__(self, out, workers, keep, proxy):
        self.workers, self.keep = workers, keep
        self.proxy = {"http": proxy, "https": proxy} if proxy else None
        self.out = open(out, "a", buffering=1, encoding="utf-8")
        self.local = threading.local()
        self.n = self.err = 0
        self.t0 = time.time()

    def sess(self):
        s = getattr(self.local, "s", None)
        if s is None:
            s = requests.Session()
            s.proxies = self.proxy or {}
            s.verify = False
            s.headers["User-Agent"] = "Mozilla/5.0"
            self.local.s = s
        return s

    def one(self, ctx):
        for attempt in range(3):
            try:
                r = self.sess().get(ctx["url"], timeout=(10, 90))
                if r.status_code != 200:
                    if r.status_code in (403, 404):
                        return {**ctx, "_fetch_error": f"http {r.status_code}"}
                    raise IOError(str(r.status_code))
                se, fe, ca, tl = parse_jsonl(r.text, self.keep)
                return {**ctx, "jsonl_bytes": len(r.content), "tool_calls": tl,
                        "n_search": len(se), "n_fetch": len(fe), "n_call": len(ca),
                        "searches": se, "fetches": fe, "calls": ca}
            except Exception as e:
                if attempt == 2:
                    return {**ctx, "_fetch_error": f"{type(e).__name__}: {str(e)[:120]}"}
                time.sleep(1 + 2 * attempt)

    def run(self, ctxs, deadline):
        batch = max(self.workers * 8, 256)
        with ThreadPoolExecutor(self.workers) as ex:
            for start in range(0, len(ctxs), batch):
                if deadline and time.time() - self.t0 > deadline:
                    print("[pause] 到时间上限，下次续跑", file=sys.stderr)
                    return
                for rec in ex.map(self.one, ctxs[start:start + batch]):
                    self.out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    self.n += 1
                    if "_fetch_error" in rec:
                        self.err += 1
                    if self.n % 1000 == 0:
                        el = time.time() - self.t0
                        print(f"[{self.n}/{len(ctxs)}] {self.n/el:.1f}/s err={self.err} "
                              f"eta={(len(ctxs)-self.n)/max(self.n/el,1e-9)/60:.0f}min",
                              file=sys.stderr, flush=True)


def load_ctx(index_dir, results, tools):
    import glob
    want = set()
    for line in open(results):
        p = line.rstrip("\n").split("\t")
        if len(p) >= 5 and (set(p[4].split(",")) & tools):
            want.add(p[0])
    print(f"[ctx] 命中 {len(want)} 个回合", file=sys.stderr)
    ctxs = []
    for path in sorted(glob.glob(os.path.join(index_dir, "index_*.tsv"))):
        with open(path, encoding="utf-8") as fh:
            head = next(fh).rstrip("\n").split("\t")
            for line in fh:
                v = line.rstrip("\n").split("\t")
                if len(v) == len(head) and v[0] in want:
                    ctxs.append(dict(zip(head, v)))
    return ctxs


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True)
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tool", default="web_search_tool")
    ap.add_argument("--keep", default="web_search_tool,web_fetch_tool")
    ap.add_argument("--workers", type=int, default=40)
    ap.add_argument("--deadline", type=int, default=0)
    ap.add_argument("--proxy", default=os.environ.get("https_proxy", ""))
    a = ap.parse_args()
    ctxs = load_ctx(a.index, a.results, {t.strip() for t in a.tool.split(",") if t.strip()})
    if os.path.exists(a.out):
        done = set()
        for line in open(a.out, encoding="utf-8"):
            try:
                done.add(json.loads(line).get("url"))
            except Exception:
                pass
        before = len(ctxs)
        ctxs = [c for c in ctxs if c["url"] not in done]
        print(f"[resume] 已完成 {before-len(ctxs)}，剩余 {len(ctxs)}", file=sys.stderr)
    f = Fetcher(a.out, a.workers, {t.strip() for t in a.keep.split(",") if t.strip()}, a.proxy)
    f.run(ctxs, a.deadline)
    print(f"[done] {f.n} 条，失败 {f.err}", file=sys.stderr)

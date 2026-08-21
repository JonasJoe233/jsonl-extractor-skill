#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stage2：流式扫全量 jsonl，标记每个回合调用了哪些工具。只做字节串匹配，不解析 JSON，所以很快。

用法：
  python3 stage2_scan.py <all_urls.txt> <results.tsv> [--tools web_search_tool,web_fetch_tool]
                         [--workers 48] [--deadline 150] [--limit N] [--proxy URL]

results.tsv 列：url / http_code / bytes / 命中第一个 tool(0|1) / 逗号分隔的全部命中 tool
已扫过的 url 自动跳过，可反复调用续跑（沙箱单次调用有墙钟上限，用 --deadline 分批）。

实测：48 线程、企业代理下约 90-110 url/s，75 万条约 2 小时；HTTP 全 200，无失败。
"""
import argparse
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests
import urllib3

urllib3.disable_warnings()


class Scanner:
    def __init__(self, out_path, workers, tools, proxy):
        self.workers, self.tools = workers, [t.encode() for t in tools]
        self.proxy = {"http": proxy, "https": proxy} if proxy else None
        self.out = open(out_path, "a", buffering=1)
        self.lock = threading.Lock()
        self.local = threading.local()
        self.done = self.hits = self.errs = self.bytes = 0
        self.t0 = time.time()

    def sess(self):
        s = getattr(self.local, "s", None)
        if s is None:
            s = requests.Session()
            s.proxies = self.proxy or {}
            s.verify = False           # 企业代理是 MITM 证书，必须关校验
            s.headers["User-Agent"] = "Mozilla/5.0"
            self.local.s = s
        return s

    def one(self, url):
        flags, size, code = set(), 0, 0
        for attempt in range(3):
            try:
                r = self.sess().get(url, stream=True, timeout=(10, 60))
                code = r.status_code
                if code != 200:
                    r.close()
                    if code in (403, 404):
                        break
                    raise IOError(f"http {code}")
                tail = b""
                for chunk in r.iter_content(1 << 18):
                    size += len(chunk)
                    buf = tail + chunk
                    for p in self.tools:
                        if p in buf:
                            flags.add(p.decode())
                    if len(flags) == len(self.tools):
                        break          # 全命中就不用读完，省带宽
                    tail = chunk[-32:]  # 跨 chunk 边界的关键词
                r.close()
                break
            except Exception:
                if attempt == 2:
                    code = -1
                else:
                    time.sleep(1 + attempt * 2)
        return url, code, size, flags

    def run(self, urls, deadline):
        first = self.tools[0].decode()
        batch = max(self.workers * 8, 512)
        with ThreadPoolExecutor(self.workers) as ex:
            for start in range(0, len(urls), batch):
                if deadline and time.time() - self.t0 > deadline:
                    print(f"[pause] 到时间上限，已完成 {self.done}，下次续跑", file=sys.stderr)
                    return
                for url, code, size, flags in ex.map(self.one, urls[start:start + batch]):
                    hit = 1 if first in flags else 0
                    self.out.write(f"{url}\t{code}\t{size}\t{hit}\t{','.join(sorted(flags))}\n")
                    with self.lock:
                        self.done += 1
                        self.hits += hit
                        self.bytes += size
                        if not 200 <= code < 300:
                            self.errs += 1
                        if self.done % 500 == 0:
                            el = time.time() - self.t0
                            rate = self.done / max(el, 1e-9)
                            print(f"[{self.done}/{len(urls)}] {rate:.1f}/s hit={self.hits} "
                                  f"err={self.errs} {self.bytes/1e9:.2f}GB "
                                  f"eta={(len(urls)-self.done)/max(rate,1e-9)/3600:.2f}h",
                                  file=sys.stderr, flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("urls")
    ap.add_argument("out")
    ap.add_argument("--tools", default="web_search_tool,web_fetch_tool")
    ap.add_argument("--workers", type=int, default=48)
    ap.add_argument("--deadline", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--proxy", default=os.environ.get("https_proxy", ""))
    a = ap.parse_args()
    urls = [l.strip() for l in open(a.urls) if l.strip()]
    total = len(urls)
    if os.path.exists(a.out):
        done = {l.split("\t", 1)[0] for l in open(a.out)}
        urls = [u for u in urls if u not in done]
        print(f"[resume] 全量 {total}，已完成 {total-len(urls)}，剩余 {len(urls)}", file=sys.stderr)
    if a.limit:
        urls = urls[:a.limit]
    tools = [t.strip() for t in a.tools.split(",") if t.strip()]
    print(f"[scan] {len(urls)} urls, {a.workers} workers, tools={tools}", file=sys.stderr)
    sc = Scanner(a.out, a.workers, tools, a.proxy)
    sc.run(urls, a.deadline)
    el = time.time() - sc.t0
    print(f"[done] {sc.done} in {el:.0f}s = {sc.done/max(el,1e-9):.1f}/s | "
          f"hits={sc.hits} errs={sc.errs} {sc.bytes/1e9:.2f}GB", file=sys.stderr)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stage1：把 Oreate agentskill CSV 压成一份精简索引，每个 assistant 回合一行。

保留全部身份/上下文字段，后面任何一步都不用再回 CSV join。user 行的 query_text
按 chat_id 前向填充到紧随其后的 assistant 回合上。

用法：
  python3 stage1_index.py --src <CSV目录> --out <输出目录>
  python3 stage1_index.py a.csv b.csv --out <输出目录>

产物：<out>/index_{day}.tsv，day 取自文件名 agentskill_{day}.csv；已存在则跳过（可续跑）。
"""
import argparse
import csv
import glob
import os
import re
import sys

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
CLEAN = re.compile(r"[\t\r\n]+")

# 想多留字段就往这里加，脚本按列名取，缺列会报错提示
COLS = ["chat_id", "message_id", "user_id", "email", "vip_type", "platform", "source_name",
        "send_time", "turnLen", "interrupt_reason", "artifact_num", "rating_1"]


def clean(s, cap=2000):
    return CLEAN.sub(" ", s)[:cap]


def one_file(path, outdir):
    base = os.path.basename(path)
    day = base[len("agentskill_"):-4] if base.startswith("agentskill_") else os.path.splitext(base)[0]
    dst = os.path.join(outdir, f"index_{day}.tsv")
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        print(f"[index] {day} 已存在，跳过", file=sys.stderr)
        return
    with open(dst + ".tmp", "w", encoding="utf-8") as out, \
         open(path, newline="", encoding="utf-8", errors="replace") as fh:
        out.write("\t".join(["url", "log_date"] + COLS + ["query_text", "artifact_infos"]) + "\n")
        r = csv.reader(l.replace("\x00", "") for l in fh)
        head = [h.lstrip("﻿") for h in next(r)]
        need = COLS + ["user_type", "query_text", "assistant_turn", "artifact_infos"]
        miss = [c for c in need if c not in head]
        if miss:
            raise SystemExit(f"[fatal] {base} 缺列 {miss}；导出模板变了，先核对列名")
        gi = {c: head.index(c) for c in need}
        pending_q, n = {}, 0
        for row in r:
            if len(row) < len(head):
                continue
            cid = row[gi["chat_id"]]
            if row[gi["user_type"]] == "user":
                q = row[gi["query_text"]].strip()
                if q:
                    pending_q[cid] = q
                continue
            url = row[gi["assistant_turn"]].strip()
            if not url.endswith(".jsonl"):
                continue
            vals = [url, day] + [clean(row[gi[c]], 200) for c in COLS]
            vals.append(clean(pending_q.get(cid, ""), 1500))
            vals.append(clean(row[gi["artifact_infos"]], 1000))
            out.write("\t".join(vals) + "\n")
            n += 1
    os.replace(dst + ".tmp", dst)
    print(f"[index] {day} -> {n} rows", file=sys.stderr, flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--src", default="")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    paths = a.files or sorted(glob.glob(os.path.join(a.src, "agentskill_*.csv")))
    if not paths:
        raise SystemExit("[fatal] 没找到输入 CSV")
    for p in paths:
        one_file(p, a.out)
    # url 全集，给 stage2 用
    seen, dst = set(), os.path.join(a.out, "all_urls.txt")
    with open(dst, "w") as fo:
        for p in sorted(glob.glob(os.path.join(a.out, "index_*.tsv"))):
            with open(p, encoding="utf-8") as fh:
                next(fh)
                for line in fh:
                    u = line.split("\t", 1)[0]
                    if u not in seen:
                        seen.add(u)
                        fo.write(u + "\n")
    print(f"[index] all_urls.txt -> {len(seen)} unique", file=sys.stderr)

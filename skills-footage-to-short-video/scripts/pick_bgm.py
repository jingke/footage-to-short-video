#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""步骤 7：挑选 BGM —— 从 Mixkit(CC0) 抓候选、下载、实测能量曲线并排序推荐。

Mixkit 授权：CC0，免费商用、无需署名、不限平台。适合短视频发布。
（Pixabay Music 页面是 JS 渲染且对爬虫 403，抓不到直链；FreePD 分类页已失效）

用法：
    # 列出候选（不下载）
    python pick_bgm.py --list --category travel

    # 下载并分析指定曲目，输出推荐排序
    python pick_bgm.py --pick "Just Keep Walking" "Summer Fun" "Discover" --out-dir bgm

选曲判据（实测，不是凭感觉）：
    1. 开头 3 秒不能是空白 —— 成片通常 1 秒内就出标题，BGM 必须立刻垫上
    2. 动态范围越小越好 —— 背景乐要平稳垫底，忽强忽弱会抢戏
    3. 时长要 >= 成片时长
"""
import os
import re
import sys
import json
import math
import array
import argparse
import subprocess
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
CATEGORIES = ["travel", "happy", "documentary", "corporate", "cinematic"]
ITEM_RE = re.compile(
    r'\{"@id":"[^"]+","@type":"MusicRecording","name":"(.*?)","genre":"(.*?)",'
    r'"byArtist":"(.*?)","duration":"(.*?)","url":"(.*?)"')
SR = 22050


def fetch(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                  timeout=40).read().decode("utf-8", "ignore")


def secs(d):
    m = re.match(r"PT(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return 0
    return int(m.group(1) or 0) * 60 + int(m.group(2) or 0)


def list_category(cat):
    html = fetch(f"https://mixkit.co/free-stock-music/{cat}/")
    return [{"name": n, "genre": g, "artist": a, "sec": secs(d), "url": u}
            for n, g, a, d, u in ITEM_RE.findall(html)]


def decode(path, dur):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-t", str(dur),
                        "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                       capture_output=True)
    a = array.array("h")
    a.frombytes(r.stdout)
    return a


def rms_db(seg):
    if not seg:
        return -99.0
    s = 0.0
    for v in seg:
        s += v * v
    return 20 * math.log10(math.sqrt(s / len(seg)) / 32768.0 + 1e-9)


def analyze(path, target_dur):
    full = decode(path, 200)
    dur = len(full) / SR
    a = decode(path, min(target_dur, dur))
    win = int(SR * 0.5)
    n = len(a) // win
    env = [rms_db(a[i * win:(i + 1) * win]) for i in range(n)]
    head = sum(env[:6]) / 6 if len(env) >= 6 else -99
    rng = max(env) - min(env) if env else 0
    # 评分：开头响度越高越好，动态范围越小越好
    score = (head + 60) * 1.0 - rng * 0.8
    return {"dur": dur, "head_db": round(head, 1), "range_db": round(rng, 1),
            "score": round(score, 1), "env": env}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="列出候选曲目")
    ap.add_argument("--category", default="travel", choices=CATEGORIES)
    ap.add_argument("--min-dur", type=int, default=70)
    ap.add_argument("--pick", nargs="+", help="要下载并分析的曲名")
    ap.add_argument("--out-dir", default="bgm")
    ap.add_argument("--target-dur", type=float, default=60)
    args = ap.parse_args()

    if args.list:
        items = list_category(args.category)
        print(f"### Mixkit / {args.category}（CC0，可商用免署名）")
        for it in items:
            if it["sec"] >= args.min_dur:
                print(f"  {it['sec']:3d}s [{it['genre']:14s}] {it['name']}  — {it['artist']}")
        print(f"\n（共 {len(items)} 首，已过滤掉短于 {args.min_dur}s 的）")
        return

    if not args.pick:
        print(__doc__)
        return

    os.makedirs(args.out_dir, exist_ok=True)
    catalog = {}
    for cat in CATEGORIES:
        try:
            for it in list_category(cat):
                catalog[it["name"]] = it
        except Exception:
            continue

    results = []
    for name in args.pick:
        it = catalog.get(name)
        if not it:
            print(f"⚠️ 未找到《{name}》，跳过")
            continue
        fn = os.path.join(args.out_dir, name.replace(" ", "_") + ".mp3")
        if not os.path.exists(fn):
            open(fn, "wb").write(urllib.request.urlopen(
                urllib.request.Request(it["url"], headers=UA), timeout=90).read())
        st = analyze(fn, args.target_dur)
        results.append({"name": name, **st, "file": fn, "genre": it["genre"]})

    results.sort(key=lambda r: -r["score"])
    print(f"\n{'曲名':<24} {'开头3s':>8} {'动态范围':>9} {'评分':>7}  判断")
    print("-" * 72)
    for i, r in enumerate(results):
        verdict = "✅ 推荐" if i == 0 else ("⚠️ 备选" if r["head_db"] > -35 else "❌ 开头空白，弃用")
        print(f"{r['name']:<24} {r['head_db']:>7.1f}dB {r['range_db']:>8.1f}dB {r['score']:>7.1f}  {verdict}")
    if results:
        best = results[0]
        print(f"\n→ 选用《{best['name']}》（{best['genre']}），文件：{best['file']}")
        print("  判据：开头最快进入状态、动态范围最小，垫底不抢戏")


if __name__ == "__main__":
    main()

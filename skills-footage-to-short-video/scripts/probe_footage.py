#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""步骤 1：探测素材规格，输出表格并给出总量评估。

用法：
    python probe_footage.py <素材目录|单个文件> [--ext .MP4]

输出：每段 文件名 / 分辨率 / 帧率 / 时长 / 大小，以及总时长、是否需要裁切的提示。
"""
import os
import sys
import json
import subprocess


def probe(path):
    r = subprocess.run([
        "ffprobe", "-v", "error",
        "-show_entries", "stream=width,height,r_frame_rate,codec_name",
        "-show_entries", "format=duration",
        "-of", "json", path,
    ], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    try:
        d = json.loads(r.stdout)
        st = next((s for s in d.get("streams", []) if "width" in s), None)
        if not st:
            return None
        num, den = st.get("r_frame_rate", "0/1").split("/")
        fps = float(num) / float(den) if float(den) else 0
        return {
            "w": st["width"], "h": st["height"], "fps": round(fps, 2),
            "codec": st.get("codec_name", "?"),
            "dur": float(d.get("format", {}).get("duration", 0)),
        }
    except Exception:
        return None


def human(size):
    for u in ("B", "K", "M", "G"):
        if size < 1024:
            return f"{size:.0f}{u}" if u == "B" else f"{size:.1f}{u}"
        size /= 1024
    return f"{size:.1f}T"


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    target = sys.argv[1]
    ext = ".mp4"
    for i, a in enumerate(sys.argv):
        if a == "--ext" and i + 1 < len(sys.argv):
            ext = sys.argv[i + 1].lower()

    if os.path.isdir(target):
        files = sorted(f for f in os.listdir(target)
                       if f.lower().endswith(ext) and not f.startswith("._"))
        files = [os.path.join(target, f) for f in files]
    else:
        files = [target]

    if not files:
        print(f"未找到 {ext} 素材：{target}")
        sys.exit(1)

    print(f"{'文件':<34} {'分辨率':>11} {'fps':>6} {'时长':>8} {'大小':>8}")
    print("-" * 72)
    total = 0.0
    res_set = set()
    for f in files:
        p = probe(f)
        sz = os.path.getsize(f)
        name = os.path.basename(f)
        if not p:
            print(f"{name:<34}  (无法解析)")
            continue
        total += p["dur"]
        res_set.add((p["w"], p["h"]))
        print(f"{name:<34} {p['w']}x{p['h']:<6} {p['fps']:>6} {p['dur']:>7.1f}s {human(sz):>8}")

    print("-" * 72)
    print(f"共 {len(files)} 段，总时长 {total:.1f}s")
    if len(res_set) == 1:
        w, h = res_set.pop()
        ratio = w / h
        kind = "横屏 16:9" if ratio > 1.5 else ("竖屏 9:16" if ratio < 0.7 else "方屏")
        print(f"统一规格：{w}x{h}（{kind}）")
        if ratio > 1.5:
            print("提示：横屏素材转竖屏需要裁切，务必逐段核对主体位置（用 contact_sheet.py）")
    else:
        print(f"警告：素材分辨率不统一 {sorted(res_set)}，需在配置里逐段指定裁切参数")


if __name__ == "__main__":
    main()

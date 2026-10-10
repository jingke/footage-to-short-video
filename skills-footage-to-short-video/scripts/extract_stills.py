#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""步骤 11a：抽静帧作社媒配图，并拼一张 contact sheet 供挑封面。

来源二选一：
  - 传**最终成片**（.mp4）：画面已烧入字幕（做封面会和标题叠字，慎用）；
  - 传**切好的段目录**（如 <work>/seg/）：脚本自动拼成一条**干净母版**（无字幕/无转场）
    再抽帧 —— **做封面首选这条**，画面干净好排版。

按均匀时间间隔抽 N 张高质量静帧（JPEG，q=2），用逐点 `-ss` 快速定位，长片也不会超时。
另输出一张缩略 contact sheet（压到 ≤0.8M px）方便肉眼挑封面。

用法：
    python extract_stills.py <成片.mp4 | seg目录> --out <目录> [--count 9] [--every 6]
"""
import os
import sys
import glob
import json
import subprocess
from PIL import Image


def build_clean_master(seg_dir, tmp_out):
    """把 seg/ 下的段拼成一条干净母版（无字幕），供抽帧。"""
    segs = sorted(glob.glob(os.path.join(seg_dir, "seg*.mp4")))
    if not segs:
        return None
    listf = tmp_out + ".txt"
    with open(listf, "w") as f:
        for s in segs:
            f.write(f"file '{os.path.abspath(s)}'\n")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                        "-i", listf, "-c", "copy", tmp_out],
                       capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(tmp_out):
        # 回退：重编码拼接
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                        "-i", listf, "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                        "-an", tmp_out], capture_output=True, text=True)
    os.remove(listf)
    return tmp_out if os.path.exists(tmp_out) else None


def probe_dur(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "json", path],
                       capture_output=True, text=True)
    try:
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return 0.0


def extract(video, out_dir, times):
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for i, t in enumerate(times, 1):
        dst = os.path.join(out_dir, f"still_{i:02d}.jpg")
        cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", video,
               "-frames:v", "1", "-q:v", "2", dst]
        rr = subprocess.run(cmd, capture_output=True, text=True)
        if rr.returncode == 0 and os.path.exists(dst):
            paths.append(dst)
        else:
            print(f"⚠️ 抽帧 {i} @ {t:.1f}s 失败")
    return paths


def make_sheet(paths, out_path, cols=3):
    if not paths:
        return None
    thumbs = [Image.open(p).convert("RGB") for p in paths]
    tw = 360
    th = int(tw * thumbs[0].height / thumbs[0].width)
    grid = [im.resize((tw, th)) for im in thumbs]
    rows = (len(grid) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * th), (20, 20, 20))
    for idx, im in enumerate(grid):
        r, c = divmod(idx, cols)
        sheet.paste(im, (c * tw, r * th))
    # 整体压到 ≤0.8M px，保证 Read 可读
    max_px = 800_000
    if sheet.width * sheet.height > max_px:
        sc = (max_px / (sheet.width * sheet.height)) ** 0.5
        sheet = sheet.resize((int(sheet.width * sc), int(sheet.height * sc)))
    sheet.save(out_path, quality=85)
    return out_path


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    video = sys.argv[1]
    out_dir = "./stills"
    count = 9
    every = 0.0
    for i, a in enumerate(sys.argv):
        if a == "--out" and i + 1 < len(sys.argv):
            out_dir = sys.argv[i + 1]
        elif a == "--count" and i + 1 < len(sys.argv):
            count = max(1, int(sys.argv[i + 1]))
        elif a == "--every" and i + 1 < len(sys.argv):
            every = float(sys.argv[i + 1])

    if not os.path.exists(video):
        print(f"❌ 找不到来源：{video}")
        sys.exit(1)

    os.makedirs(out_dir, exist_ok=True)
    # 传目录（seg/）→ 先拼干净母版再抽帧（无字幕，封面首选）
    if os.path.isdir(video):
        clean = build_clean_master(video, os.path.join(out_dir, "_clean_master.mp4"))
        if not clean:
            print(f"❌ {video} 下没有 seg*.mp4")
            sys.exit(1)
        print(f"已拼干净母版（无字幕）：{clean}")
        video = clean

    dur = probe_dur(video)
    if dur <= 0:
        print("⚠️ 取不到时长，退而求其次均匀抽 9 张")
        dur = 90.0

    if every > 0:
        times = [round(every * k, 3) for k in range(int(dur // every))]
        if not times:
            times = [dur / 2]
    else:
        # 均匀分布在 (0, dur) 之间，避开最头最尾
        pad = dur * 0.04
        times = [round(pad + (dur - 2 * pad) * (k + 0.5) / count, 3)
                 for k in range(count)]
        times = [t for t in times if t < dur]

    print(f"从 {video}（{dur:.1f}s）抽 {len(times)} 张静帧 → {out_dir}")
    paths = extract(video, out_dir, times)
    sheet = make_sheet(paths, os.path.join(out_dir, "stills_sheet.jpg"))
    print(f"完成 {len(paths)} 张：")
    for p in paths:
        print(f"  {p}")
    if sheet:
        print(f"封面候选拼图：{sheet}（读它挑 best still 做封面）")


if __name__ == "__main__":
    main()

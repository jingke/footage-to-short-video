#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""步骤 3：按配置裁切/缩放素材，输出到 <work_dir>/seg/segNN.mp4（无音轨）。

- 画幅一致时只做 scale，不裁切
- 画幅不一致时按目标比例裁切（默认居中，可用 clip.crop_x / crop_y 覆盖）
  ⚠️ 裁切位置必须用 contact_sheet.py 逐段核对主体，别盲目居中

用法：
    python cut_clips.py config.json [--force]
"""
import os
import sys
import json
import subprocess


def probe_wh(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height",
                        "-of", "csv=p=0:s=x", path], capture_output=True, text=True)
    try:
        w, h = r.stdout.strip().split("x")
        return int(w), int(h)
    except Exception:
        return 0, 0


def build_vf(src_w, src_h, out_w, out_h, clip):
    tr = out_w / out_h
    sr = src_w / src_h
    if abs(sr - tr) < 0.01:
        return f"scale={out_w}:{out_h}:flags=lanczos"
    if sr > tr:
        # 源更宽 → 裁宽度
        cw = int(round(src_h * tr))
        cw -= cw % 2
        x = clip.get("crop_x", (src_w - cw) // 2)
        x = max(0, min(x, src_w - cw))
        return f"crop={cw}:{src_h}:{x}:0,scale={out_w}:{out_h}:flags=lanczos"
    else:
        # 源更高 → 裁高度
        ch = int(round(src_w / tr))
        ch -= ch % 2
        y = clip.get("crop_y", (src_h - ch) // 2)
        y = max(0, min(y, src_h - ch))
        return f"crop={src_w}:{ch}:0:{y},scale={out_w}:{out_h}:flags=lanczos"


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cfg = json.load(open(sys.argv[1]))
    force = "--force" in sys.argv

    src_dir = cfg["source_dir"]
    work = cfg["work_dir"]
    seg_dir = os.path.join(work, "seg")
    os.makedirs(seg_dir, exist_ok=True)

    out_w, out_h = cfg["out_w"], cfg["out_h"]
    fps = cfg.get("fps", 30)
    crf = cfg.get("crf", 16)

    for i, c in enumerate(cfg["clips"], 1):
        dst = os.path.join(seg_dir, f"seg{i:02d}.mp4")
        src = c["file"] if os.path.isabs(c["file"]) else os.path.join(src_dir, c["file"])
        if os.path.exists(dst) and not force:
            print(f"seg{i:02d} 已存在，跳过（--force 强制重切）")
            continue
        if not os.path.exists(src):
            print(f"❌ 找不到 {src}")
            sys.exit(1)
        sw, sh = probe_wh(src)
        vf = build_vf(sw, sh, out_w, out_h, c)
        cmd = ["ffmpeg", "-v", "error", "-y", "-ss", str(c["ss"]), "-t", str(c["dur"]),
               "-i", src, "-vf", f"{vf},fps={fps},setsar=1",
               "-c:v", "libx264", "-crf", str(crf), "-preset", "fast",
               "-pix_fmt", "yuv420p", "-an", dst]
        note = c.get("note", "")
        print(f"→ seg{i:02d}  {os.path.basename(src)}  ss={c['ss']} t={c['dur']}  {note}")
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stderr[-2000:])
            sys.exit(1)
    total = sum(c["dur"] for c in cfg["clips"]) - cfg.get("xfade", 0.5) * (len(cfg["clips"]) - 1)
    print(f"\n完成 {len(cfg['clips'])} 段 → {seg_dir}   预计成片 {total:.2f}s")


if __name__ == "__main__":
    main()

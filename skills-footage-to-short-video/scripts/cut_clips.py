#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""步骤 3：按配置裁切/缩放素材，输出到 <work_dir>/seg/segNN.mp4（无音轨）。

- 画幅一致时只做 scale，不裁切
- 画幅不一致时按目标比例裁切（默认居中，可用 clip.crop_x / crop_y 覆盖）
  ⚠️ 裁切位置必须用 contact_sheet.py 逐段核对主体，别盲目居中

进阶：可选关键帧推拉（Ken Burns）
  在 clip 上加 "kenburns" 字段即可（剪映「关键帧」的 ffmpeg 等价，用 zoompan 实现）：
    "kenburns": true                         # 默认缓慢推近 1.0→1.15
    "kenburns": {"zoom": 1.2, "dir": "in", "pan": "right"}
      zoom: 最大放大倍数（默认 1.15，建议 ≤1.3，越大越糊）
      dir : "in"（推近，默认）/ "out"（拉远）
      pan : "center"(默认) / "left" / "right" / "up" / "down" 缓慢平移方向
  实现方式：先把片段超采样放大到 out×zoom，再用 zoompan 缓慢缩小回 out 并平移，
  全程在画面内取样，不会露黑边。

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


def build_vf(src_w, src_h, out_w, out_h, clip, fps):
    tr = out_w / out_h
    sr = src_w / src_h
    crop_part = ""
    if abs(sr - tr) >= 0.01:
        if sr > tr:
            # 源更宽 → 裁宽度
            cw = int(round(src_h * tr))
            cw -= cw % 2
            x = clip.get("crop_x", (src_w - cw) // 2)
            x = max(0, min(x, src_w - cw))
            crop_part = f"crop={cw}:{src_h}:{x}:0"
        else:
            # 源更高 → 裁高度
            ch = int(round(src_w / tr))
            ch -= ch % 2
            y = clip.get("crop_y", (src_h - ch) // 2)
            y = max(0, min(y, src_h - ch))
            crop_part = f"crop={src_w}:{ch}:0:{y}"

    km = clip.get("kenburns")
    if km:
        kb = km if isinstance(km, dict) else {}
        zm = float(kb.get("zoom", 1.15))
        direction = (kb.get("dir") or "in").lower()
        pan = (kb.get("pan") or "center").lower()
        fps = int(fps)
        dur = float(clip.get("dur", 5))
        N = max(2, int(round(dur * fps)))
        # 超采样：先放大到 out×zoom，给 zoompan 留出取样余量，避免露黑边
        owz = int(round(out_w * zm)); owz -= owz % 2
        ohz = int(round(out_h * zm)); ohz -= ohz % 2
        base = f"scale={owz}:{ohz}:flags=lanczos"
        # 缩放表达式：随输出帧号 on 从 1 线性变到 zoom
        if direction == "out":
            z_exp = f"max(1.0, {zm} - ({zm}-1)*on/{N})"
        else:
            z_exp = f"min({zm}, 1.0 + ({zm}-1)*on/{N})"
        # 平移偏移：margin 为取样余量，随 on 从中心滑向某一侧（始终在画面内）
        mx = "(iw-iw/zoom)/2"
        my = "(ih-ih/zoom)/2"
        if pan == "right":
            x_exp = f"iw/2 - iw/zoom/2 + {mx}*(on/{N})"
        elif pan == "left":
            x_exp = f"iw/2 - iw/zoom/2 - {mx}*(on/{N})"
        else:
            x_exp = "iw/2 - iw/zoom/2"
        if pan == "up":
            y_exp = f"ih/2 - ih/zoom/2 - {my}*(on/{N})"
        elif pan == "down":
            y_exp = f"ih/2 - ih/zoom/2 + {my}*(on/{N})"
        else:
            y_exp = "ih/2 - ih/zoom/2"
        zp = (f"zoompan=z='{z_exp}':d=1:x='{x_exp}':y='{y_exp}'"
              f":s={out_w}x{out_h}:fps={fps}")
        if crop_part:
            return f"{crop_part},{base},{zp}"
        return f"{base},{zp}"

    base = f"scale={out_w}:{out_h}:flags=lanczos"
    if crop_part:
        return f"{crop_part},{base}"
    return base


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
        vf = build_vf(sw, sh, out_w, out_h, c, fps)
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

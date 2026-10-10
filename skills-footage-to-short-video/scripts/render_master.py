#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""步骤 5：拼合母版 —— 交叉溶解 + 字幕层叠加 + 首尾淡入淡出。

输出 <work_dir>/master_silent.mp4（无音轨）。后续混 BGM 时用 -c:v copy，画面不二次压缩。

用法：
    python render_master.py config.json [--out custom_name.mp4]
"""
import os
import sys
import json
import subprocess


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cfg = json.load(open(sys.argv[1]))
    work = cfg["work_dir"]
    seg_dir = os.path.join(work, "seg")
    cap_dir = os.path.join(work, "caps")
    n = len(cfg["clips"])
    xf = cfg.get("xfade", 0.5)
    fade = cfg.get("cap_fade", 0.35)

    for i in range(1, n + 1):
        if not os.path.exists(os.path.join(seg_dir, f"seg{i:02d}.mp4")):
            print(f"❌ 缺少 seg{i:02d}.mp4，先跑 cut_clips.py")
            sys.exit(1)

    t = cfg["title"]
    layers = [("title.png", t["start"], t["end"])]
    layers += [(f"cap{i:02d}.png", c["start"], c["end"])
               for i, c in enumerate(cfg["captions"], 1)]

    total = sum(c["dur"] for c in cfg["clips"]) - xf * (n - 1)
    print(f"规划总时长 {total:.2f}s，字幕层 {len(layers)} 个")

    cmd = ["ffmpeg", "-v", "warning", "-y"]
    for i in range(1, n + 1):
        cmd += ["-i", os.path.join(seg_dir, f"seg{i:02d}.mp4")]
    for name, s, e in layers:
        cmd += ["-loop", "1", "-t", f"{e - s:.3f}", "-i", os.path.join(cap_dir, name)]

    fc = []
    prev = "[0:v]"
    off = 0.0
    for i in range(1, n):
        off += cfg["clips"][i - 1]["dur"] - xf
        out = f"[x{i}]"
        fc.append(f"{prev}[{i}:v]xfade=transition=fade:duration={xf}:offset={off:.3f}{out}")
        prev = out

    for idx, (name, s, e) in enumerate(layers):
        inp = f"[{n + idx}:v]"
        tag = f"[o{idx}]"
        st = max(e - s - fade, 0)
        fc.append(f"{inp}fade=t=in:st=0:d={fade}:alpha=1,"
                  f"fade=t=out:st={st:.3f}:d={fade}:alpha=1,"
                  f"setpts=PTS-STARTPTS+{s:.3f}/TB{tag}")
        nxt = f"[v{idx}]"
        fc.append(f"{prev}{tag}overlay=0:0:enable='between(t,{s:.3f},{e:.3f})'{nxt}")
        prev = nxt

    fi = cfg.get("fade_in", 0.6)
    fo = cfg.get("fade_out", 0.7)
    fc.append(f"{prev}fade=t=in:st=0:d={fi},fade=t=out:st={total - fo:.3f}:d={fo},"
              f"format=yuv420p[vout]")

    out_name = "master_silent.mp4"
    if "--out" in sys.argv:
        out_name = sys.argv[sys.argv.index("--out") + 1]
    out_path = os.path.join(work, out_name)

    cmd += ["-filter_complex", ";".join(fc), "-map", "[vout]",
            "-c:v", "libx264", "-crf", str(cfg.get("render_crf", 21)),
            "-preset", cfg.get("preset", "medium"),
            "-maxrate", cfg.get("maxrate", "8M"),
            "-bufsize", cfg.get("bufsize", "16M"),
            "-profile:v", "high", "-level", "4.1", "-r", str(cfg.get("fps", 30)),
            "-movflags", "+faststart", "-an", out_path]

    print("渲染中…")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("FFMPEG 失败：")
        print(r.stderr[-4000:])
        sys.exit(1)
    print("完成 ->", out_path)


if __name__ == "__main__":
    main()

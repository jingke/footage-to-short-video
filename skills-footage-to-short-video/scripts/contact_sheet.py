#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""步骤 2：抽帧拼图，用来看清每段素材拍了什么、主体在哪。

这一步不可跳过 —— 字幕文案要靠它写，竖屏裁切位置要靠它定。

用法：
    # 对每个视频均匀抽 3 帧，拼成一张总览图
    python contact_sheet.py <素材目录> --out sheet.jpg

    # 叠加竖屏裁切窗口，验证主体是否被切掉（绿框=候选位置）
    python contact_sheet.py <素材目录> --out sheet.jpg --crop 9:16 --crop-x 1312 1100 1500

    # 单文件、指定时间点
    python contact_sheet.py <视频文件> --times 2 6 9 --crop 9:16 --crop-x 1312
"""
import os
import sys
import glob
import argparse
import subprocess
import tempfile
from PIL import Image, ImageDraw

FONT_CANDIDATES = [
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]


def load_font(size=22):
    from PIL import ImageFont
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def ffprobe_duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
                        path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def grab(video, t, out):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", video,
                    "-frames:v", "1", "-vf", "scale=800:-2", out], check=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="素材目录或单个视频文件")
    ap.add_argument("--out", default="sheet.jpg")
    ap.add_argument("--per", type=int, default=3, help="每个视频抽几帧")
    ap.add_argument("--times", nargs="+", type=float, help="指定时间点（单文件模式）")
    ap.add_argument("--ext", default=".mp4")
    ap.add_argument("--crop", help="画幅比例，如 9:16 或 16:9")
    ap.add_argument("--crop-x", nargs="+", type=int, help="裁切窗口左边界像素（源分辨率坐标系）")
    ap.add_argument("--src-w", type=int, help="源宽度（默认从素材读取）")
    ap.add_argument("--width", type=int, default=560, help="每格显示宽度")
    args = ap.parse_args()

    if os.path.isdir(args.target):
        files = sorted(glob.glob(os.path.join(args.target, "*" + args.ext)))
        files = [f for f in files if not os.path.basename(f).startswith("._")]
    else:
        files = [args.target]
    if not files:
        print("未找到素材")
        sys.exit(1)

    tmpdir = tempfile.mkdtemp()
    font = load_font(20)
    rows = []
    cols = [(255, 80, 80), (60, 255, 120), (90, 170, 255), (255, 210, 60)]

    for f in files:
        dur = ffprobe_duration(f)
        if args.times:
            ts = args.times
        else:
            if dur <= 0:
                continue
            # 均匀取点，避开首尾
            ts = [round(dur * (i + 1) / (args.per + 1), 2) for i in range(args.per)]

        ims = []
        for t in ts:
            out = os.path.join(tmpdir, f"{len(ims)}.png")
            try:
                grab(f, min(t, max(dur - 0.1, 0)), out)
            except Exception:
                continue
            im = Image.open(out).convert("RGB")
            W, H = im.size

            if args.crop and args.crop_x is not None:
                ar = args.crop.split(":")
                ratio = float(ar[0]) / float(ar[1])
                src_w = args.src_w or W
                cw = int(H * ratio)
                d = ImageDraw.Draw(im)
                for k, x0 in enumerate(args.crop_x):
                    sx = int(x0 * W / src_w)
                    scw = int(cw * W / src_w)
                    c = cols[k % len(cols)]
                    d.rectangle([sx, 0, sx + scw, H - 1], outline=c, width=3)
                    d.text((sx + 5, 6), str(x0), font=font, fill=c)
            ims.append((t, im))
        if ims:
            rows.append((os.path.basename(f), dur, ims))

    if not rows:
        print("抽帧失败")
        sys.exit(1)

    tw = args.width
    first_h = rows[0][2][0][1].height
    th = int(first_h * tw / rows[0][2][0][1].width)
    gap = 8
    ncol = max(len(r[2]) for r in rows)
    sheet = Image.new("RGB", (ncol * (tw + gap) + gap, len(rows) * (th + gap) + gap), (18, 18, 22))
    d = ImageDraw.Draw(sheet)

    for r, (name, dur, ims) in enumerate(rows):
        y = r * (th + gap) + gap
        d.text((gap + 4, y + 4), f"{name}  ({dur:.1f}s)", font=font, fill=(255, 220, 60))
        for c, (t, im) in enumerate(ims):
            x = c * (tw + gap) + gap
            sheet.paste(im.resize((tw, th), Image.LANCZOS), (x, y))
            d.text((x + 4, y + th - 24), f"{t}s", font=font, fill=(255, 255, 255))

    sheet.save(args.out, quality=90)
    print(f"已生成 {args.out}  ({sheet.size[0]}x{sheet.size[1]})  共 {len(rows)} 段")


if __name__ == "__main__":
    main()

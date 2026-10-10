#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""步骤 6：生成封面。

两种版式：
  left   —— 左侧暗渐变 + 左对齐标题（画面中央有主体人物时用，避开人物）
  bottom —— 底部暗渐变 + 居中标题（竖屏常用）

底图取自 seg/segNN.mp4（已切好的片段），无需回读 4K 源。

用法：
    python make_cover.py config.json [--out cover.jpg] [--ts 4] [--clip-index 0]
"""
import os
import sys
import json
import subprocess
import tempfile
from PIL import Image, ImageDraw, ImageFont


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def auto_font():
    for p in ("/System/Library/Fonts/STHeiti Medium.ttc",
              "/System/Library/Fonts/STHeiti Light.ttc",
              "/System/Library/Fonts/Hiragino Sans GB.ttc",
              "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
              "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
              "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
              "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
              "C:/Windows/Fonts/msyh.ttc"):
        if os.path.exists(p):
            return p
    raise SystemExit("找不到中文字体，请在 config 的 font 字段指定")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    argv = sys.argv
    cfg = json.load(open(argv[1]))
    work = cfg["work_dir"]
    W, H = cfg["out_w"], cfg["out_h"]
    cv = cfg.get("cover", {})

    def opt(name, default):
        return argv[argv.index(name) + 1] if name in argv else default

    idx = int(opt("--clip-index", cv.get("clip_index", 0))) + 1
    ts = float(opt("--ts", cv.get("ts", 2)))
    out_path = opt("--out", os.path.join(work, "cover.jpg"))

    seg = os.path.join(work, "seg", f"seg{idx:02d}.mp4")
    if not os.path.exists(seg):
        print(f"❌ 缺少 {seg}")
        sys.exit(1)

    frame = os.path.join(tempfile.gettempdir(), "_cover_src.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(ts), "-i", seg,
                    "-frames:v", "1", frame], check=True)

    src = Image.open(frame).convert("RGB")
    canvas = src.resize((W, H), Image.LANCZOS)

    FONT = cfg.get("font") or auto_font()
    WHITE = (255, 255, 255)
    GOLD = hex_rgb(cfg.get("gold", "F0BA4E"))
    SHADOW = (0, 0, 0, 200)

    layout = cv.get("layout", "left" if W > H else "bottom")
    im = canvas.convert("RGBA")
    d = ImageDraw.Draw(im, "RGBA")

    def f(sz):
        return ImageFont.truetype(FONT, sz)

    if layout == "left":
        scrim = Image.new("L", (W, H), 0)
        sd = ImageDraw.Draw(scrim)
        x_end = int(W * 0.62)
        for x in range(x_end):
            sd.line([(x, 0), (x, H)], fill=int(216 * (1 - x / float(x_end)) ** 1.05))
        im = Image.composite(Image.new("RGB", (W, H), (4, 6, 12)),
                             im.convert("RGB"), scrim).convert("RGBA")
        d = ImageDraw.Draw(im, "RGBA")

        x = int(W * 0.068)
        f_en = f(round(H * 0.028))
        d.rounded_rectangle([x, int(H * 0.278), x + round(H * 0.0075), int(H * 0.298)],
                            radius=4, fill=GOLD)
        d.text((x + round(H * 0.028), int(H * 0.280)), cv.get("en", ""), font=f_en, fill=GOLD)

        f1 = f(round(H * 0.087))
        d.text((x + 4, int(H * 0.344) + 5), cv["line1"], font=f1, fill=SHADOW)
        d.text((x, int(H * 0.344)), cv["line1"], font=f1, fill=WHITE)
        d.rounded_rectangle([x, int(H * 0.474), x + int(W * 0.058), int(H * 0.480)],
                            radius=3, fill=GOLD)

        f2 = f(round(H * 0.044))
        hl = cv.get("highlight")
        yy = int(H * 0.524)
        cur = x
        if hl and hl in cv["line2"]:
            pre, post = cv["line2"].split(hl, 1)
        else:
            pre, post, hl = cv["line2"], "", None
        for t, c in ((pre, WHITE), (hl, GOLD), (post, WHITE)):
            if not t:
                continue
            d.text((cur + 3, yy + 4), t, font=f2, fill=SHADOW)
            d.text((cur, yy), t, font=f2, fill=c)
            cur += d.textbbox((0, 0), t, font=f2)[2]
    else:
        scrim = Image.new("L", (W, H), 0)
        sd = ImageDraw.Draw(scrim)
        y0 = int(H * 0.55)
        for y in range(y0, H):
            sd.line([(0, y), (W, y)], fill=int(238 * ((y - y0) / (H - y0)) ** 0.85))
        im = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)),
                             im.convert("RGB"), scrim).convert("RGBA")
        d = ImageDraw.Draw(im, "RGBA")

        cx = W // 2
        f1 = f(round(W * 0.089))
        f2 = f(round(W * 0.048))
        y1 = int(H * 0.748)

        def line(y, text, fo, hl=None):
            if hl and hl in text:
                pre, post = text.split(hl, 1)
                tw = sum(d.textbbox((0, 0), t, font=fo)[2] for t in (pre, hl, post))
                cur = cx - tw / 2
                for t, c in ((pre, WHITE), (hl, GOLD), (post, WHITE)):
                    if t:
                        d.text((cur + 3, y + 4), t, font=fo, fill=SHADOW)
                        d.text((cur, y), t, font=fo, fill=c)
                        cur += d.textbbox((0, 0), t, font=fo)[2]
            else:
                d.text((cx + 3, y + 4), text, font=fo, fill=SHADOW, anchor="ma")
                d.text((cx, y), text, font=fo, fill=WHITE, anchor="ma")

        line(y1, cv["line1"], f1)
        d.rounded_rectangle([cx - int(W * 0.052), int(H * 0.812),
                             cx + int(W * 0.052), int(H * 0.815)], radius=3, fill=GOLD)
        line(int(H * 0.821), cv["line2"], f2, hl=cv.get("highlight"))

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    im.convert("RGB").save(out_path, "JPEG", quality=94)
    os.remove(frame)
    print(f"{out_path}  ({W}x{H})  版式={layout}")


if __name__ == "__main__":
    main()

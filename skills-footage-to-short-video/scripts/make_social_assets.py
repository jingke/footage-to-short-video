#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""步骤 11b：把选中的静帧 + 标题拼成社媒封面/头图（PIL，无需 libass）。

- 小红书封面：1080×1440（3:4），标题大字 + 金色副标题，底部暗渐变保证可读
- 公众号头图：1080×460（≈2.35:1），左侧标题 + 副标题

用法：
    python make_social_assets.py <still.jpg> --title "..." [--subtitle "..."] \
        [--font /path.ttc] [--gold F0BA4E] [--out <dir>]

字体缺省自动探测中文字体；gold 为金色高亮色（同视频金色字）。
"""
import os
import sys
import argparse
from PIL import Image, ImageDraw, ImageFont


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
    raise SystemExit("找不到中文字体，请用 --font 指定")


def load_font(path, size):
    # ttc 多字重：优先取第 0 个；失败则回退默认
    try:
        return ImageFont.truetype(path, size, index=0)
    except Exception:
        return ImageFont.load_default()


def wrap_cjk(draw, text, font, max_w):
    """按字符宽度把中文/中英文混排文本折行。"""
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        trial = cur + ch
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def cover_fit(img, W, H):
    """等比缩放并居中裁切到 W×H（cover）。"""
    sw, sh = img.size
    scale = max(W / sw, H / sh)
    nw, nh = int(sw * scale), int(sh * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    x = (nw - W) // 2
    y = (nh - H) // 2
    return img.crop((x, y, x + W, y + H))


def bottom_gradient(W, H, max_alpha=180, start=0.5):
    """底部暗渐变（透明→黑），height 比例 start 处起渐变。"""
    grad = Image.new("L", (1, H))
    px = []
    for y in range(H):
        a = 0.0
        if y > H * start:
            a = (y - H * start) / (H * (1 - start)) * max_alpha
        px.append(int(min(max_alpha, a)))
    grad.putdata(px)
    return grad.resize((W, H))


def compose(still, W, H, title, subtitle, font_path, gold, out_path,
            title_sz, sub_sz, title_color=(255, 255, 255)):
    base = cover_fit(Image.open(still).convert("RGB"), W, H)
    base = base.convert("RGBA")
    grad = bottom_gradient(W, H)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    overlay.putalpha(grad)
    base = Image.alpha_composite(base, overlay)

    draw = ImageDraw.Draw(base)
    pad = int(W * 0.07)
    content_w = W - 2 * pad

    # 标题（白色大字，按宽折行）
    tf = load_font(font_path, title_sz)
    title_lines = wrap_cjk(draw, title, tf, content_w)
    # 副标题（金色）
    sf = load_font(font_path, sub_sz)
    sub_lines = wrap_cjk(draw, subtitle, sf, content_w) if subtitle else []

    lh_t = int(title_sz * 1.18)
    lh_s = int(sub_sz * 1.3)
    block_h = len(title_lines) * lh_t + (len(sub_lines) * lh_s if sub_lines else 0)
    x = pad
    y = H - pad - block_h

    g = tuple(int(gold[i:i + 2], 16) for i in (0, 2, 4))
    for ln in title_lines:
        draw.text((x, y), ln, font=tf, fill=title_color)
        y += lh_t
    y += int(sub_sz * 0.2)
    for ln in sub_lines:
        draw.text((x, y), ln, font=sf, fill=g)
        y += lh_s

    base.convert("RGB").save(out_path, quality=90)
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("still")
    ap.add_argument("--title", required=True)
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--font", default="")
    ap.add_argument("--gold", default="F0BA4E")
    ap.add_argument("--out", default=".")
    a = ap.parse_args()

    font = a.font or auto_font()
    os.makedirs(a.out, exist_ok=True)

    xhs = compose(a.still, 1080, 1440, a.title, a.subtitle, font, a.gold,
                  os.path.join(a.out, "xhs_cover.jpg"), 80, 42)
    wx = compose(a.still, 1080, 460, a.title, a.subtitle, font, a.gold,
                 os.path.join(a.out, "wechat_header.jpg"), 60, 30)
    print("小红书封面 ->", xhs)
    print("公众号头图 ->", wx)


if __name__ == "__main__":
    main()

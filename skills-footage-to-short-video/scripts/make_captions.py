#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""步骤 4：用 PIL 渲染透明字幕层 PNG（绕过 ffmpeg 缺 libass 的问题）。

输出 <work_dir>/caps/title.png 与 capNN.png。
【】内的文字自动用金色高亮。

⚠️ 为什么不用 ffmpeg 的 subtitles/ass/drawtext 滤镜：
   很多 brew/apt 安装的 ffmpeg 没编译 libass 与 freetype，这三个滤镜根本不存在。
   PIL 渲染透明层 + overlay 叠加是跨平台通用方案，且版式控制更自由。

用法：
    python make_captions.py config.json
"""
import os
import sys
import json
from PIL import Image, ImageDraw, ImageFont, ImageFilter


def hex_rgba(h, a=255):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (a,)


def default_layout(W, H):
    """按画幅给出经过实测的版式参数"""
    if H > W:      # 竖屏 9:16
        return {
            "cap_size": round(W * 0.048), "big_size": round(W * 0.048),
            "title_size": round(H * 0.048), "en_size": round(H * 0.0166),
            "bar_cy": round(H * 0.715),
            "en_y": round(H * 0.195), "zh_y": round(H * 0.234), "div_y": round(H * 0.275),
            "max_text_w": round(W * 0.833), "scrim": (200, 640, 120),
        }
    else:          # 横屏 16:9（字号必须相对放大，否则手机上过小）
        return {
            "cap_size": round(W * 0.040), "big_size": round(W * 0.045),
            "title_size": round(H * 0.085), "en_size": round(H * 0.031),
            "bar_cy": round(H * 0.807),
            "en_y": round(H * 0.256), "zh_y": round(H * 0.324), "div_y": round(H * 0.393),
            "max_text_w": round(W * 0.844), "scrim": (140, 500, 118),
        }


def parse(text):
    out, buf, hl = [], "", False
    for ch in text:
        if ch == "【":
            if buf:
                out.append((buf, hl))
            buf, hl = "", True
        elif ch == "】":
            if buf:
                out.append((buf, hl))
            buf, hl = "", False
        else:
            buf += ch
    if buf:
        out.append((buf, hl))
    return out


class CaptionRenderer:
    def __init__(self, cfg):
        self.cfg = cfg
        self.W, self.H = cfg["out_w"], cfg["out_h"]
        lay = default_layout(self.W, self.H)
        lay.update(cfg.get("layout", {}))
        self.L = lay
        self.font_path = cfg.get("font") or self._auto_font()
        self.WHITE = (255, 255, 255, 255)
        self.GOLD = hex_rgba(cfg.get("gold", "F0BA4E"))
        self.SHADOW = (0, 0, 0, 190)
        self.BARC = (10, 12, 18, 150)

    def _auto_font(self):
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
        raise SystemExit("找不到中文字体，请在 config 的 font 字段显式指定")

    def f(self, sz):
        return ImageFont.truetype(self.font_path, sz)

    def layer(self):
        im = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        return im, ImageDraw.Draw(im, "RGBA")

    def _measure(self, d, segs, f):
        return [d.textbbox((0, 0), t, font=f, anchor="ls")[2] for t, _ in segs]

    def _draw_line(self, d, cx, y, segs, f):
        ws = self._measure(d, segs, f)
        x = cx - sum(ws) / 2.0
        for (t, is_hl), w in zip(segs, ws):
            col = self.GOLD if is_hl else self.WHITE
            d.text((x + 3, y + 4), t, font=f, fill=self.SHADOW, anchor="ls")
            d.text((x, y), t, font=f, fill=col, anchor="ls")
            x += w
        return sum(ws)

    def _autofit(self, text, max_w, start):
        tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
        sz = start
        while sz > start * 0.6:
            f = self.f(sz)
            if sum(self._measure(tmp, parse(text), f)) <= max_w:
                return sz
            sz -= 2
        return sz

    def top_scrim(self, im):
        y0, y1, peak = self.L["scrim"]
        y0, y1 = int(y0), int(y1)
        a = Image.new("L", (1, self.H), 0)
        px = a.load()
        mid = (y0 + y1) // 2
        for y in range(y0, min(y1, self.H)):
            t = 1 - abs(y - mid) / float(mid - y0)
            px[0, y] = int(peak * max(0.0, t) ** 0.85)
        a = a.resize((self.W, self.H)).filter(ImageFilter.GaussianBlur(44))
        im.alpha_composite(Image.merge("RGBA", (
            Image.new("L", (self.W, self.H), 0), Image.new("L", (self.W, self.H), 0),
            Image.new("L", (self.W, self.H), 0), a)))

    def build_title(self, path):
        t = self.cfg["title"]
        im, d = self.layer()
        self.top_scrim(im)
        cx = self.W // 2
        f_en = self.f(self.L["en_size"])
        en = " ".join(t["en"])
        d.text((cx + 2, self.L["en_y"] + 3), en, font=f_en, fill=(0, 0, 0, 170), anchor="mm")
        d.text((cx, self.L["en_y"]), en, font=f_en, fill=self.GOLD, anchor="mm")
        f_zh = self.f(self.L["title_size"])
        d.text((cx + 4, self.L["zh_y"] + 5), t["main"], font=f_zh, fill=self.SHADOW, anchor="mm")
        d.text((cx, self.L["zh_y"]), t["main"], font=f_zh, fill=self.WHITE, anchor="mm")
        hw = round(self.W * 0.061)
        d.rounded_rectangle([cx - hw, self.L["div_y"] - 3, cx + hw, self.L["div_y"] + 3],
                            radius=3, fill=self.GOLD)
        im.save(path)

    def build_caption(self, path, text, big=False):
        sz = self._autofit(text, self.L["max_text_w"],
                           self.L["big_size"] if big else self.L["cap_size"])
        f = self.f(sz)
        segs = parse(text)
        im, d = self.layer()
        cx = self.W // 2
        tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
        w = sum(self._measure(tmp, segs, f))

        pad_x = round(sz * 0.78)
        pad_y = round(sz * 0.45)
        bw = w + pad_x * 2
        asc, desc = f.getmetrics()
        bh = asc + desc + pad_y * 2
        cy = self.L["bar_cy"]
        x0, y0 = cx - bw / 2, cy - bh / 2
        x1, y1 = cx + bw / 2, cy + bh / 2

        r = round(bh * 0.18)
        d.rounded_rectangle([x0 + 5, y0 + 9, x1 + 5, y1 + 9], radius=r, fill=(0, 0, 0, 95))
        d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=self.BARC)
        d.rounded_rectangle([x0 + round(pad_x * 0.36), y0 + round(bh * 0.1),
                             x0 + round(pad_x * 0.36) + round(sz * 0.14), y1 - round(bh * 0.1)],
                            radius=4, fill=self.GOLD)
        baseline = y1 - pad_y - desc
        self._draw_line(d, cx + round(sz * 0.15), baseline, segs, f)
        im.save(path)

    def run(self):
        caps = os.path.join(self.cfg["work_dir"], "caps")
        os.makedirs(caps, exist_ok=True)
        self.build_title(os.path.join(caps, "title.png"))
        print("title.png")
        for i, c in enumerate(self.cfg["captions"], 1):
            p = os.path.join(caps, f"cap{i:02d}.png")
            self.build_caption(p, c["text"], big=(i == len(self.cfg["captions"])))
            print(f"cap{i:02d}.png  {c['start']}-{c['end']}  {c['text']}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cfg = json.load(open(sys.argv[1]))
    CaptionRenderer(cfg).run()


if __name__ == "__main__":
    main()

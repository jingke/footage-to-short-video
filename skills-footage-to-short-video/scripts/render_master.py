#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""步骤 5：拼合母版 —— 转场 + 字幕层叠加 + 画中画 + 暗角 + 首尾淡入淡出。

输出 <work_dir>/master_silent.mp4（无音轨）。后续混 BGM 时用 -c:v copy，画面不二次压缩。

转场（transitions）：
  - 缺省或写 "auto" → 自动选择（见 auto_transitions）：依每段 motion/reveal 标签挑合适的，
    并保证不是千篇一律的 fade
  - 写列表（长度 = 段数−1）→ 逐切点手动指定
  可用：fade / smoothleft / smoothright / slideleft / slideup /
        circleopen / circleclose / radial / distance / fadeblack

进阶特效（可选，默认关）：
  - pips[]    画中画：把另一段素材缩放在角落/中央，指定时间段叠加（剪映「画中画」的 ffmpeg 等价）
  - vignette  暗角：cinematic 暗角（剪映「蒙版/暗角」的 ffmpeg 等价），默认不开启

用法：
    python render_master.py config.json [--out custom_name.mp4]
"""
import os
import sys
import json
import subprocess

# 每种转场对应的推荐时长
TYPE_DUR = {
    "fade": 0.5, "smoothleft": 0.6, "smoothright": 0.6, "slideleft": 0.5,
    "slideup": 0.5, "circleopen": 0.7, "circleclose": 0.7, "radial": 0.7,
    "distance": 0.6, "fadeblack": 0.6,
}
VALID_TRANS = set(TYPE_DUR) | {"fade"}


def auto_transitions(clips, n):
    """按语义 + 多样性自动选转场，保证不千篇一律。"""
    res = []
    for i in range(1, n):
        out_c, in_c = clips[i - 1], clips[i]
        m = (out_c.get("motion") or "").lower()
        if m in ("pan", "push"):          # 前一段是「向前运镜/推进」→ 横向推移，呼应位移
            t = "smoothleft"
        elif m == "orbit":                # 环绕 → 圆形展开
            t = "circleopen"
        elif in_c.get("reveal"):          # 后一段是「揭幕式大景」→ 横向拉开
            t = "smoothleft"
        else:
            t = "fade"
        res.append(t)
    # 若全是 fade，按 1/3 节奏注入 smoothleft，制造自然的变化
    fade_idx = [k for k, t in enumerate(res) if t == "fade"]
    if len(fade_idx) >= n - 1:
        for k in fade_idx:
            if k % 3 == 1:
                res[k] = "smoothleft"
    return res


def _probe_wh(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height",
                        "-of", "csv=p=0:s=x", path], capture_output=True, text=True)
    try:
        w, h = r.stdout.strip().split("x")
        return int(w), int(h)
    except Exception:
        return 0, 0


def build_pip(src, dst, out_w, out_h, p):
    """把一段素材缩成画中画小窗（保持原比例，fit 进盒内；含可选白边），输出到 dst。

    返回 (成功, 实际宽, 实际高)。实际尺寸按源比例在盒子内等比缩放，避免拉伸变形。
    """
    box_w = int(out_w * p.get("scale", 0.3))
    box_h = int(out_h * p.get("scale", 0.3))
    sw, sh = _probe_wh(src)
    if sw and sh:
        src_ar = sw / sh
        box_ar = box_w / box_h
        if src_ar > box_ar:          # 源更宽 → 以盒宽为准
            tw = box_w
            th = int(round(box_w / src_ar))
        else:                        # 源更高 → 以盒高为准
            th = box_h
            tw = int(round(box_h * src_ar))
    else:
        tw, th = box_w, box_h
    tw -= tw % 2
    th -= th % 2
    vf = f"scale={tw}:{th}:flags=lanczos"
    b = p.get("border", 0)
    if b:
        vf += f",drawbox=w=iw:h=ih:t={int(b)}:color=white@0.9"
    vf += ",setsar=1"
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", str(p["ss"]), "-t", str(p["dur"]),
           "-i", src, "-vf", vf, "-c:v", "libx264", "-crf", "23", "-preset", "fast",
           "-pix_fmt", "yuv420p", dst]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0, tw, th


def pip_geometry(out_w, out_h, pw, ph, p):
    """返回画中画的位置表达式（角落 / 中央，可叠加漂移）。"""
    margin = int(out_w * p.get("margin", 0.05))
    corner = (p.get("corner") or "br").lower()
    if corner in ("center", "mid"):
        bx = (out_w - pw) // 2
        by = (out_h - ph) // 2
    elif corner in ("tl", "topleft"):
        bx, by = margin, margin
    elif corner in ("tr", "topright"):
        bx, by = out_w - pw - margin, margin
    elif corner in ("bl", "bottomleft"):
        bx, by = margin, out_h - ph - margin
    else:  # br / bottomright
        bx, by = out_w - pw - margin, out_h - ph - margin
    a0, a1 = p["at"]
    if p.get("animate") == "drift":
        x_expr = f"({bx}) + 12*sin((t-{a0})*2.0)"
        y_expr = f"({by}) + 8*cos((t-{a0})*1.5)"
    else:
        x_expr, y_expr = str(bx), str(by)
    return x_expr, y_expr


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
    auto_xf = cfg.get("auto_xfade_dur", 0.5)

    L = len(cfg["captions"]) + 1  # 标题 + 字幕

    # --- 转场类型与时长 ---
    tr_cfg = cfg.get("transitions")
    if tr_cfg is None or (isinstance(tr_cfg, str) and tr_cfg.lower() == "auto"):
        tr = auto_transitions(cfg["clips"], n)
    elif isinstance(tr_cfg, str):
        tr = [tr_cfg] * (n - 1)
    else:
        tr = list(tr_cfg) + ["fade"] * ((n - 1) - len(tr_cfg))
    tr = [t if t in VALID_TRANS else "fade" for t in tr]

    xfd = cfg.get("xfade_dur") or []
    if isinstance(xfd, (int, float)):
        xfd = [float(xfd)] * (n - 1)
    xfd = [float(v) for v in xfd] + [xf] * ((n - 1) - len(xfd))

    def tname(i):
        return tr[i] or "fade"

    def tdur(i):
        if xfd[i]:
            return xfd[i]
        return float(TYPE_DUR.get(tname(i), auto_xf))

    for i in range(1, n + 1):
        if not os.path.exists(os.path.join(seg_dir, f"seg{i:02d}.mp4")):
            print(f"❌ 缺少 seg{i:02d}.mp4，先跑 cut_clips.py")
            sys.exit(1)

    t = cfg["title"]
    layers = [("title.png", t["start"], t["end"])]
    layers += [(f"cap{i:02d}.png", c["start"], c["end"])
               for i, c in enumerate(cfg["captions"], 1)]

    total = sum(tdur(i) for i in range(n - 1))
    total = sum(c["dur"] for c in cfg["clips"]) - total
    print(f"规划总时长 {total:.2f}s，字幕层 {len(layers)} 个，转场 {tr}")

    # --- 画中画预生成 ---
    pips = cfg.get("pips") or []
    pip_paths = []
    pip_meta = []
    if pips:
        os.makedirs(os.path.join(work, "pip"), exist_ok=True)
        for k, p in enumerate(pips):
            src = p["file"] if os.path.isabs(p["file"]) else os.path.join(cfg["source_dir"], p["file"])
            dst = os.path.join(work, "pip", f"pip{k}.mp4")
            ok, pw, ph = build_pip(src, dst, cfg["out_w"], cfg["out_h"], p)
            if not ok:
                print(f"⚠️ 画中画 {k} 生成失败，跳过")
                continue
            pip_paths.append(dst)
            x_expr, y_expr = pip_geometry(cfg["out_w"], cfg["out_h"], pw, ph, p)
            pip_meta.append((k, x_expr, y_expr, p["at"]))

    cmd = ["ffmpeg", "-v", "warning", "-y"]
    for i in range(1, n + 1):
        cmd += ["-i", os.path.join(seg_dir, f"seg{i:02d}.mp4")]
    for name, s, e in layers:
        cmd += ["-loop", "1", "-t", f"{e - s:.3f}", "-i", os.path.join(cap_dir, name)]
    for p in pip_paths:
        cmd += ["-i", p]

    fc = []
    prev = "[0:v]"
    off = 0.0
    for i in range(1, n):
        d = tdur(i - 1)
        off += cfg["clips"][i - 1]["dur"] - d
        out = f"[x{i}]"
        fc.append(f"{prev}[{i}:v]xfade=transition={tname(i - 1)}:duration={d}"
                  f":offset={off:.3f}{out}")
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

    # 画中画叠加（在字幕之上）：prev 为主画面（背景），pip 为前景叠加
    for k, x_expr, y_expr, (a0, a1) in pip_meta:
        pi = n + L + k
        prev = (f"{prev}[{pi}:v]overlay=enable='between(t,{a0},{a1})'"
                f":x={x_expr}:y={y_expr}[pv{k}]")
        fc.append(prev)
        prev = f"[pv{k}]"

    fi = cfg.get("fade_in", 0.6)
    fo = cfg.get("fade_out", 0.7)
    tail = (f"{prev}fade=t=in:st=0:d={fi},fade=t=out:st={total - fo:.3f}:d={fo},"
            f"format=yuv420p")
    vig = cfg.get("vignette")
    if vig:
        # 暗角强度 v(0~1)：映射成镜头角度 angle，v 越大暗角越重（角度越小）。
        # ffmpeg 的 vignette 滤镜用 angle（默认 PI/5≈0.628，角度越小暗角越深）。
        v = min(float(vig), 0.95)
        ang = max(0.08, (3.14159265 / 5.0) * (1.0 - v))
        tail += f",vignette=angle={ang:.3f}"
    tail += "[vout]"
    fc.append(tail)

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

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""步骤 1：探测素材规格，输出表格并给出总量评估。

用法：
    python probe_footage.py <素材目录|单个文件> [--ext .MP4] [--confirm]

输出：每段 文件名 / 分辨率 / 帧率 / 时长 / 大小，以及总时长、是否需要裁切的提示。

⚠️ 大文件预警（人工确认）：
    凡单段 大小 ≥ 2 GB 或 时长 ≥ 300 s，会被标记为「大文件」。
    这类素材若直接跑抽帧/分析/切片，可能解码数十分钟甚至超时（见 references/pitfalls.md）。
    脚本会打印醒目预警块，列出所有大文件及累计体量；agent 在跑后续重步骤前，
    必须先用 AskUserQuestion 让用户确认（确认继续 / 先抽小样验证 / 跳过该文件）。
    带 --confirm 表示已获人工确认，仅抑制「需要人工确认」提示，预警块仍会打印。
"""
import os
import sys
import json
import subprocess

# 大文件阈值：单段大小 ≥ 2GB，或单段时长 ≥ 300s
SIZE_THRESH = 2 * 1024 ** 3
DUR_THRESH = 300.0


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
    confirm = "--confirm" in sys.argv
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

    print(f"{'文件':<34} {'分辨率':>11} {'fps':>6} {'时长':>8} {'大小':>8} {'大文件':>5}")
    print("-" * 80)
    total = 0.0
    total_size = 0
    res_set = set()
    big = []  # (name, size, dur)
    for f in files:
        p = probe(f)
        sz = os.path.getsize(f)
        name = os.path.basename(f)
        total_size += sz
        if not p:
            print(f"{name:<34}  (无法解析)")
            continue
        total += p["dur"]
        res_set.add((p["w"], p["h"]))
        is_big = (sz >= SIZE_THRESH) or (p["dur"] >= DUR_THRESH)
        if is_big:
            big.append((name, sz, p["dur"]))
        flag = "🔴" if is_big else ""
        print(f"{name:<34} {p['w']}x{p['h']:<6} {p['fps']:>6} {p['dur']:>7.1f}s "
              f"{human(sz):>8} {flag:>5}")

    print("-" * 80)
    print(f"共 {len(files)} 段，总时长 {total:.1f}s，总大小 {human(total_size)}")
    if len(res_set) == 1:
        w, h = res_set.pop()
        ratio = w / h
        kind = "横屏 16:9" if ratio > 1.5 else ("竖屏 9:16" if ratio < 0.7 else "方屏")
        print(f"统一规格：{w}x{h}（{kind}）")
        if ratio > 1.5:
            print("提示：横屏素材转竖屏需要裁切，务必逐段核对主体位置（用 contact_sheet.py）")
    else:
        print(f"警告：素材分辨率不统一 {sorted(res_set)}，需在配置里逐段指定裁切参数")

    # --- 大文件人工确认预警 ---
    if big:
        print()
        print("=" * 80)
        print("⚠️  大文件预警：以下素材单段 ≥ 2GB 或 ≥ 300s，重处理前需【人工确认】")
        print("=" * 80)
        big_size = sum(s for _, s, _ in big)
        for name, sz, dur in big:
            reason = []
            if sz >= SIZE_THRESH:
                reason.append(f"体积 {human(sz)} ≥ 2GB")
            if dur >= DUR_THRESH:
                reason.append(f"时长 {dur:.0f}s ≥ 300s")
            print(f"  🔴 {name:<32}  {'；'.join(reason)}")
        print("-" * 80)
        print(f"  大文件合计 {len(big)} 段，{human(big_size)}")
        print("  风险：直接抽帧/分析/切片段可能解码数十分钟或超时（长片段勿用 fps+tile 全解）。")
        print("  处理建议（agent 须先征得用户同意，再跑后续步骤）：")
        print("    1) 确认继续 —— 已知悉耗时，直接处理；")
        print("    2) 先抽小样 —— 用 contact_sheet.py 的 --ss 定点抽帧，验证内容再决定；")
        print("    3) 跳过该文件 —— 从素材清单剔除，不纳入成片。")
        if not confirm:
            print("  ⛔ 未带 --confirm：请人工确认后再继续，本脚本只做轻量 ffprobe 不解码画面。")
        else:
            print("  ✅ 已带 --confirm：人工已确认，可继续。")
        print("=" * 80)


if __name__ == "__main__":
    main()

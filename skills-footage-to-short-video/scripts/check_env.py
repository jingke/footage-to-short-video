#!/usr/bin/env python3
"""步骤 -1：环境自检。

检查 footage-to-short-video 所需依赖是否齐备，缺什么就打印对应的安装命令。
只读检查，不修改任何东西。

用法：
    python3 scripts/check_env.py            # 人可读报告
    python3 scripts/check_env.py --json     # 机器可读
退出码：必需项全齐 = 0，缺必需项 = 1
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# 流水线真正会用到的滤镜，缺一个就没法出片
REQUIRED_FILTERS = ["xfade", "overlay", "fade", "amix", "scale", "crop", "setsar"]
# 可选：有则能直接用 ass/subtitles/drawtext 烧字幕，没有就走 PIL 字幕层
OPTIONAL_FILTERS = ["subtitles", "ass", "drawtext"]

# PIL 渲染字幕时要显式指定字体文件，按平台给出候选
FONT_CANDIDATES = [
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
    "C:/Windows/Fonts/msyh.ttc",
]

# 可选：自建的带 libass 版本
LIBASS_CANDIDATES = [
    os.path.expanduser("~/.workbuddy/bin/ffmpeg"),
    os.path.expanduser("~/.workbuddy/ffmpeg/bin/ffmpeg"),
    "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
]


def sh(cmd: list[str], timeout: int = 20) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except FileNotFoundError:
        return 127, "not found"
    except subprocess.TimeoutExpired:
        return 124, "timeout"


def ffmpeg_path() -> str | None:
    code, out = sh(["ffmpeg", "-version"])
    return None if code != 0 else (out.splitlines()[0] if out else "ffmpeg")


def has_filters(ffmpeg: str, names: list[str]) -> dict[str, bool]:
    code, out = sh([ffmpeg, "-hide_banner", "-filters"])
    if code != 0:
        return {n: False for n in names}
    present: set[str] = set()
    for line in out.splitlines():
        parts = line.split()
        # 形如 " .. crop" / " T. afade" / "TS fade" —— 标志位 1~3 个字符，其后紧跟滤镜名
        if len(parts) >= 3 and parts[0] and set(parts[0]) <= set("TSC."):
            present.add(parts[1])
    return {n: (n in present) for n in names}


def check_pillow() -> tuple[bool, str]:
    try:
        import PIL  # noqa: F401
        from PIL import ImageFont  # noqa: F401

        return True, f"Pillow {PIL.__version__}"
    except Exception:
        return False, "未安装（pip install Pillow）"


def find_font() -> str | None:
    for p in FONT_CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


def find_libass_ffmpeg() -> str | None:
    for p in LIBASS_CANDIDATES:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            code, _ = sh([p, "-version"])
            if code == 0:
                return p
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="footage-to-short-video 环境自检")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    ff = ffmpeg_path()
    result: dict = {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "ffmpeg": ff,
        "ffprobe": sh(["ffprobe", "-version"])[0] == 0,
    }

    required_ok = True

    # ffmpeg 必需滤镜
    if ff:
        rf = has_filters("ffmpeg", REQUIRED_FILTERS)
        of = has_filters("ffmpeg", OPTIONAL_FILTERS)
    else:
        rf = {n: False for n in REQUIRED_FILTERS}
        of = {n: False for n in OPTIONAL_FILTERS}
        required_ok = False
    result["required_filters"] = rf
    result["optional_filters"] = of
    if not all(rf.values()):
        required_ok = False

    # ffprobe
    if not result["ffprobe"]:
        required_ok = False

    # Pillow
    pillow_ok, pillow_msg = check_pillow()
    result["pillow"] = pillow_msg
    result["pillow_ok"] = pillow_ok
    if not pillow_ok:
        required_ok = False

    # 字体
    font = find_font()
    result["font"] = font
    if not font:
        required_ok = False

    # 可选的 libass 版本
    libass = find_libass_ffmpeg()
    result["ffmpeg_libass"] = libass
    if libass:
        result["ffmpeg_libass_filters"] = has_filters(libass, OPTIONAL_FILTERS)

    result["required_ok"] = required_ok

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if required_ok else 1

    def mark(ok: bool, optional: bool = False) -> str:
        if ok:
            return "✅"
        return "⚪" if optional else "❌"

    print("=" * 62)
    print("footage-to-short-video 环境自检")
    print("=" * 62)

    print(f"\n[必需]")
    print(f"  {mark(bool(ff))} ffmpeg            {ff or '未找到 → brew install ffmpeg / apt install ffmpeg'}")
    print(f"  {mark(result['ffprobe'])} ffprobe           {'ok' if result['ffprobe'] else '未找到（随 ffmpeg 一起装）'}")
    missing = [n for n, ok in rf.items() if not ok]
    print(f"  {mark(not missing)} 滤镜              {'全部具备' if not missing else '缺失: ' + ', '.join(missing)}")
    print(f"  {mark(pillow_ok)} Pillow            {pillow_msg}")
    print(f"  {mark(bool(font))} 中文字体          {font or '未找到系统 CJK 字体'}")

    print(f"\n[可选]")
    opt_missing = [n for n, ok in of.items() if not ok]
    if not opt_missing:
        print(f"  ✅ 系统 ffmpeg 自带字幕滤镜（subtitles/ass/drawtext）")
    else:
        print(f"  ⚪ 系统 ffmpeg 缺字幕滤镜（{', '.join(opt_missing)}）")
        print(f"     → 不影响出片：本技能用 PIL 渲染字幕层")
        if libass:
            print(f"  ✅ 找到带 libass 的 ffmpeg：{libass}")
            lf = result.get("ffmpeg_libass_filters", {})
            print(f"     滤镜: " + ", ".join(f"{k}={'✅' if v else '❌'}" for k, v in lf.items()))
        else:
            print(f"  ⚪ 未找到带 libass 的 ffmpeg（需要时见 references/ffmpeg-with-libass.md）")

    print()
    if required_ok:
        print("结论：✅ 必需依赖齐备，可以开工。")
        return 0

    print("结论：❌ 缺少必需依赖，按下面装：")
    if not ff or not result["ffprobe"]:
        print("  macOS:   brew install ffmpeg")
        print("  Ubuntu:  sudo apt install ffmpeg")
        print("  Windows: winget install Gyan.FFmpeg")
    if not pillow_ok:
        print("  python3 -m pip install Pillow")
    if not font:
        print("  安装一款中文字体（macOS 自带；Linux: apt install fonts-noto-cjk）")
    print("\n完整说明见 references/setup.md")
    return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""步骤 8：把 BGM 混入无音轨母版，并做响度校准。

关键：用 -c:v copy 直拷画面，不二次压缩，画质零损失、速度极快。

响度目标（短视频平台通用）：
    - 纯 BGM、无人声：-17 ~ -18 LUFS
    - 有人声/旁白：-14 ~ -16 LUFS
    ⚠️ 不要压到 -23 LUFS 以下：平台上传后会二次增益，容易顶到削波

用法：
    python mix_audio.py config.json                      # 用 config 里的 bgm 配置
    python mix_audio.py config.json --bgm x.mp3 --vol -1.5
    python mix_audio.py config.json --check              # 只检测响度，不混音
"""
import os
import sys
import json
import subprocess
import argparse


def loudness(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", path,
                        "-af", "loudnorm=print_format=summary", "-f", "null", "-"],
                       capture_output=True, text=True)
    out = {}
    for line in r.stderr.splitlines():
        if "Input Integrated" in line:
            out["lufs"] = float(line.split(":")[1].strip().split()[0])
        elif "Input True Peak" in line:
            out["tp"] = float(line.split(":")[1].strip().split()[0])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--bgm", help="覆盖 config 中的 BGM 路径")
    ap.add_argument("--vol", type=float, help="覆盖音量 dB")
    ap.add_argument("--master", help="覆盖无音轨母版路径")
    ap.add_argument("--out", help="输出文件名")
    ap.add_argument("--check", action="store_true", help="只检测响度")
    args = ap.parse_args()

    cfg = json.load(open(args.config))
    work = cfg["work_dir"]

    if args.check:
        for f in (args.master, args.out):
            if f and os.path.exists(f):
                m = loudness(f)
                print(f"{f}: {m.get('lufs')} LUFS / {m.get('tp')} dBTP")
        return

    master = args.master or os.path.join(work, "master_silent.mp4")
    bgm_cfg = cfg.get("bgm", {})
    bgm = args.bgm or bgm_cfg.get("file")
    if bgm and not os.path.isabs(bgm):
        bgm = os.path.join(work, bgm)
    if not bgm or not os.path.exists(bgm):
        print(f"❌ BGM 不存在：{bgm}\n   先用 pick_bgm.py 下载，或在 config.bgm.file 指定")
        sys.exit(1)
    if not os.path.exists(master):
        print(f"❌ 母版不存在：{master}\n   先跑 render_master.py")
        sys.exit(1)

    dur = sum(c["dur"] for c in cfg["clips"]) - cfg.get("xfade", 0.5) * (len(cfg["clips"]) - 1)
    vol = args.vol if args.vol is not None else bgm_cfg.get("volume_db", -1.5)
    fi = bgm_cfg.get("fade_in", 0.8)
    fo_at = bgm_cfg.get("fade_out_at", dur - 1.7)
    fo_dur = bgm_cfg.get("fade_out_dur", 1.7)

    out = args.out or os.path.join(work, "final.mp4")
    af = (f"[1:a]atrim=0:{dur:.2f},asetpts=PTS-STARTPTS,volume={vol}dB,"
          f"afade=t=in:st=0:d={fi},afade=t=out:st={fo_at:.2f}:d={fo_dur},"
          f"alimiter=limit=0.89,aresample=48000[a]")

    cmd = ["ffmpeg", "-v", "error", "-y", "-i", master, "-i", bgm,
           "-filter_complex", af, "-map", "0:v", "-map", "[a]",
           "-c:v", "copy", "-c:a", "aac", "-b:a", cfg.get("audio_bitrate", "192k"),
           "-shortest", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-3000:])
        sys.exit(1)

    m = loudness(out)
    lufs = m.get("lufs")
    print(f"完成 -> {out}")
    print(f"响度 {lufs} LUFS / {m.get('tp')} dBTP")
    if lufs is not None:
        if lufs < -20:
            print("⚠️ 响度偏低，平台二次增益可能削波。建议调高 volume_db（每 +6dB ≈ +6 LUFS）")
        elif lufs > -13:
            print("⚠️ 响度偏高，可能被平台压限。建议调低 volume_db")
        else:
            print("✅ 响度落在短视频平台舒适区")


if __name__ == "__main__":
    main()

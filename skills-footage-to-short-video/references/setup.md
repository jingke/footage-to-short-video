# 依赖安装手册

本技能的依赖刻意保持很轻：**ffmpeg + Python 标准库 + Pillow**。
其余全部用 `os / json / subprocess / math / array / urllib` 搞定，不需要 numpy、requests 或任何 API Key。

## 先跑自检

```bash
python3 scripts/check_env.py            # 人可读报告
python3 scripts/check_env.py --json     # 机器可读
```

退出码 `0` = 必需依赖齐备；`1` = 缺东西，脚本会直接打印对应的安装命令。
**开始任何项目之前先跑一次。**

## 依赖总览

| 依赖 | 必需性 | 谁在用 | 说明 |
|---|---|---|---|
| **ffmpeg** | ✅ 必需 | 全部脚本 | 探测、裁切、拼合、混音、抽帧 |
| **ffprobe** | ✅ 必需 | probe_footage | 随 ffmpeg 一起安装 |
| ffmpeg 滤镜 `xfade / overlay / fade / amix / scale / crop / setsar` | ✅ 必需 | render_master、cut_clips | 任何完整版 ffmpeg 都自带 |
| **Python 3.9+** | ✅ 必需 | 全部脚本 | 仅用标准库 |
| **Pillow** | ✅ 必需 | make_captions、make_cover、contact_sheet | 渲染字幕层与封面 |
| **中文字体** | ✅ 必需 | make_captions、make_cover | macOS 自带；Linux 需装 Noto CJK |
| ffmpeg 滤镜 `subtitles / ass / drawtext` | ⚪ 可选 | 仅当你想用 ASS 烧字幕 | 缺了不影响出片，默认走 PIL |
| 带 libass 的自建 ffmpeg | ⚪ 可选 | 对话级字幕场景 | 见 `ffmpeg-with-libass.md` |
| 网络 | ⚪ 可选 | pick_bgm | 抓 Mixkit CC0 曲库，离线时可跳过该步 |

⚠️ **不依赖** numpy（音频分析用 `array` + `math`，实测 numpy 在受限沙箱里会 SIGTERM）。

## macOS

```bash
# 1. ffmpeg / ffprobe
brew install ffmpeg

# 2. Python + Pillow（装进隔离 venv，别污染系统 Python）
python3 -m venv ~/.workbuddy/binaries/python/envs/default
~/.workbuddy/binaries/python/envs/default/bin/pip install Pillow

# 3. 中文字体：macOS 自带，无需安装
#    常用：/System/Library/Fonts/STHeiti Medium.ttc
#         /System/Library/Fonts/Supplemental/Songti.ttc
```

### ⚠️ brew 版 ffmpeg 是精简版

`brew install ffmpeg`（homebrew 核心配方）**不含 libass / libfreetype / fontconfig**，
所以 `subtitles`、`ass`、`drawtext` 三个滤镜不存在。

**这不是问题** —— 本技能用 PIL 渲染字幕层，不依赖这三个滤镜。
只有在你要处理「几十上百条对话字幕」时才需要补，方法见 `ffmpeg-with-libass.md`。

想装 `ffmpeg-full`（官方的 47 依赖完整版）也可以，但在受限环境里往往装不上：
brew 倒 bottle 时嵌套 `sandbox-exec` 会被拒（`sandbox_apply: Operation not permitted`）。

## Linux（Debian / Ubuntu）

```bash
sudo apt update
sudo apt install -y ffmpeg python3-pil fonts-noto-cjk
```

Ubuntu 的 ffmpeg **通常已编译 libass**，`check_env.py` 会把 `subtitles/ass` 报为 ✅。
若发行版版本太老（缺 `xfade`），改用官方静态构建或自行编译。

```bash
sudo apt install -y fonts-wqy-zenhei   # 文泉驿，可选替代字体
```

## Windows

```powershell
winget install Gyan.FFmpeg          # 官方构建，含 libass
python -m pip install Pillow
```

字体用 `C:/Windows/Fonts/msyh.ttc`（微软雅黑）或 `simhei.ttf`，
写在 config 的 `font` 字段，脚本的自动探测也包含这两个路径。

## 中文字体：跨平台怎么处理

两个脚本（`make_captions.py`、`make_cover.py`）都按 config 的 `font` 字段加载，
没填就自动探测，顺序为：

1. macOS：`STHeiti Medium.ttc` → `STHeiti Light.ttc` → `Hiragino Sans GB.ttc` → `Arial Unicode.ttf`
2. Linux：`NotoSansCJK-Regular.ttc`（opentype / truetype 两个位置）→ `wqy-zenhei.ttc`
3. Windows：`C:/Windows/Fonts/msyh.ttc`

都找不到就报 `找不到中文字体，请在 config 的 font 字段显式指定` —— 此时手动填绝对路径即可。

## 常见安装问题

| 现象 | 原因 | 处理 |
|---|---|---|
| `ModuleNotFoundError: No module named 'PIL'` | 脚本用的 Python 不是装了 Pillow 的那个 | 用同一个解释器：`~/.workbuddy/binaries/python/envs/default/bin/python scripts/xxx.py` |
| `找不到中文字体` | 无 CJK 字体 | Linux 装 `fonts-noto-cjk`；或 config 里显式写 `font` |
| `No such filter: 'xfade'` | ffmpeg 太老（< 4.3） | 升级 ffmpeg |
| `No such filter: 'subtitles'` | 精简版 ffmpeg | 正常，走 PIL 字幕层；要 ASS 见 `ffmpeg-with-libass.md` |
| pip 装 numpy 被 SIGTERM / exit 137 | 受限沙箱 | 不需要 numpy，跳过 |
| pick_bgm 报网络错误 | 无外网或 Mixkit 被墙 | 手动提供 BGM 文件，跳过步骤 7 |

## 最小可用组合验证

```bash
python3 scripts/check_env.py
# 期望：ffmpeg ✅ / ffprobe ✅ / 滤镜 ✅ / Pillow ✅ / 中文字体 ✅
```

只要这五行全 ✅，整条流水线（除了联网挑曲）就能跑通。

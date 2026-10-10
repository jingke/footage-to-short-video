---
name: footage-to-short-video
description: 把一批视频素材（DJI 无人机、相机、手机拍摄的旅拍/活动/探店 B-roll）剪辑成可发布的短视频成片——裁切画幅、生成中文字幕、配 BGM、做封面、校准码率与响度，输出竖屏 9:16 与横屏 16:9 双版本。当用户提供多个视频文件并要求「剪一个短视频」「做成视频号/抖音能发的片子」「加字幕配 BGM」「把这段素材剪出来」时应使用本技能。
agent_created: true
---

# 素材转短视频流水线

## Overview

把一堆原始素材变成可直接发布的短视频。全流程本地完成，不依赖剪映等 GUI 软件，
也不需要任何 API Key。

核心能力：素材探测 → 抽帧看懂内容 → 裁切画幅 → PIL 渲染字幕（绕过 ffmpeg 缺
libass 的问题）→ 交叉溶解拼合 → 挑 BGM 并校准响度 → 生成封面。

## 前置检查

**开工前先跑环境自检**（缺什么它会直接给出安装命令）：

```bash
python3 scripts/check_env.py
```

需要 **ffmpeg / ffprobe** 与 **Python 3 + Pillow**，其余只用标准库（**不依赖 numpy**）。
各平台的完整安装步骤、跨平台字体处理、常见问题见 **`references/setup.md`**。

### 关于字幕：两条路，按需选

| 场景 | 用什么 | 说明 |
|---|---|---|
| 少量精致文字卡（默认） | **PIL 渲染透明层 + overlay** | 不依赖 ffmpeg 编译选项，版式自由 |
| 几十上百条对话字幕 | **带 libass 的 ffmpeg** | 一个字幕文件管全片，`-vf "ass=sub.ass"` |

本机已自建好带 libass 的版本，路径 `~/.workbuddy/bin/ffmpeg`
（构建过程与验证命令见 `references/ffmpeg-with-libass.md`）。
**默认别用它替换 PATH**——它缺 libvpx / x265 / dav1d 等外部库，不是系统 ffmpeg 的超集。
需要时显式调用或临时 `export PATH="$HOME/.workbuddy/bin:$PATH"`。

## 工作流

### 步骤 0：确认三件事（用 AskUserQuestion，别猜）

| 要问的 | 选项 |
|---|---|
| 画幅 | 竖屏 9:16（信息流推荐）/ 横屏 16:9 / 两个都要 |
| 时长 | 约 30s（快剪）/ **约 60s（推荐）** / 约 90s |
| BGM | 用户提供文件 / 联网找 CC0 免费曲 / 先出不配乐版 |

拿到答案后再开工。若用户未指定，默认竖屏 + 60s + 联网找 CC0 曲。

### 步骤 1：探测素材

```bash
python scripts/probe_footage.py <素材目录> --ext .MP4
```

拿到每段的分辨率、帧率、时长、大小，以及总时长。素材分辨率不统一时，
后续需逐段指定裁切参数。

⚠️ **大文件预警**：凡单段 体积 ≥ 2GB 或 时长 ≥ 300s，表格里会用 🔴 标出，
脚本末尾还会打印一个醒目预警块（列清单 + 累计体量 + 处理建议）。
这类素材直接抽帧/分析/切片可能解码数十分钟甚至超时（长片段切勿用 `fps+tile`
全量解码，见 `references/pitfalls.md`）。看到预警，**先走步骤 1.5**。

### 步骤 1.5：大文件人工确认（看到 🔴 才需要）

当步骤 1 标出大文件时，**在跑步骤 2（抽帧）/ 分析 / 步骤 4（切片段）之前，
必须先用 AskUserQuestion 让用户确认**，不要自作主张一次性解码数 GB/数百秒素材。
给用户三个选项：

| 选项 | 含义 |
|---|---|
| 确认继续 | 用户已知悉耗时，直接处理（后续命令可带 `--confirm` 抑制提示） |
| 先抽小样 | 用 `contact_sheet.py --ss <秒>` 定点抽几帧验证内容，再决定 |
| 跳过该文件 | 把该段从素材清单里剔除，不纳入成片 |

只有用户选了「确认继续」才往下走；选「跳过」就改 config 去掉该段。

### 步骤 2：抽帧看内容（不可跳过）

```bash
python scripts/contact_sheet.py <素材目录> --out sheet.jpg --per 3
```

**必须看图后再写字幕文案**，凭文件名猜几乎一定写错。生成的拼图直接读进来逐段看。

若转竖屏，同时验证裁切窗口：

```bash
python scripts/contact_sheet.py <素材目录> --out sheet.jpg \
    --crop 9:16 --crop-x 1100 1312 1500 --src-w 3840
```

绿/红/蓝框是三个候选裁切位置，确认主体（尤其人脸）在框内后，把选定值写进
config 的 `crop_x`。

### 步骤 3：写配置文件

复制 `assets/project_config.example.json` 到工作目录并改写。字段说明见模板内注释。

关键字段：
- `clips[]` — 每段 `ss`（起点）、`dur`（时长）、可选 `crop_x` / `crop_y`
  - `motion` 标签（可选）：`"pan"` / `"push"`（向前运镜/推进）、`"orbit"`（环绕）。
    写给 `transitions:"auto"` 当路标——auto 会据此把对应切点换成 `smoothleft` / `circleopen`。
  - `reveal`（可选，布尔）：后一段若是「揭幕式大景」，auto 会在进点用 `smoothleft` 横向拉开。
  - `kenburns`（可选）：关键帧推拉（剪映「关键帧」的 ffmpeg 等价，用 `zoompan` 实现）。
    写 `true` 即默认缓慢推近 1.0→1.15；或写对象 `{"zoom":1.2,"dir":"in|out","pan":"center|left|right|up|down"}`。
    **zoom 建议 ≤1.3**，越大越糊；实现先超采样放大再缩回，全程在画面内取样，不会露黑边。
- `transitions` — 可选，两种写法：
  - 写 **`"auto"`**（推荐）：脚本按每段 `motion` / `reveal` 标签挑合适转场，
    并保证不是千篇一律的 `fade`（全是 fade 时按 1/3 节奏注入 `smoothleft`）。
  - 写列表（长度 = 段数−1）：逐切点手动指定。
  可用转场：`fade`（交叉溶解，最稳）、`smoothleft` / `smoothright`（横向推移，呼应「向前行进」）、
  `slideleft` / `slideup`、`circleopen` / `circleclose`（圆形展开/收拢，呼应环绕）、
  `radial`、`distance`、`fadeblack`。
  **全片一种转场会显单调；即使手动指定，也建议以 `fade` 为主，只在语义转折处换 2~4 个方向性转场。**
- `xfade_dur[]` — 可选，逐切点转场时长（缺省按转场类型取 0.5~0.7s）
- `captions[]` — 字幕 `start` / `end` / `text`，【】内文字自动金色高亮
- `title` — 主标题与英文小字
- `pips[]` — 可选，**画中画**（剪映「画中画」的 ffmpeg 等价）：把另一段素材缩放成小窗，
  在指定时间段叠加到角落/中央。每项：`{file, ss, dur, scale(默认0.3), corner(tl/tr/bl/br/center),
  margin(默认0.05), border(白边像素,可选), at:[起始,结束]秒, animate:"drift"(可选轻微漂移)}`。
- `vignette` — 可选，**暗角/蒙版感**（剪映「蒙版/暗角」的 ffmpeg 等价）：写 0.1~0.5 的强度值
  （越大暗角越重，`0.2`~`0.3` 较自然），让中心更突出、画面更电影感。默认不开启。
  （内部映射到 `vignette` 滤镜的 `angle` 参数，越小越深。）

> 剪映原生的「关键帧 / 画中画 / 蒙版」交互更细，但本 skill 已用 ffmpeg 提供等价能力：
> 关键帧推拉 = `kenburns`（zoompan）、画中画 = `pips[]`、蒙版/暗角 = `vignette`。
> 若成片还要更精修，可把母版导入剪映手动微调，但默认流程已能出彩。

时间轴计算：总时长 = Σ`dur` − Σ转场时长。字幕时间基于这个时间轴。
文案写法见 `references/caption-writing.md`。

### 步骤 4：切片段

```bash
python scripts/cut_clips.py config.json
```

画幅一致时只缩放不裁切；不一致时按目标比例裁切（默认居中，被 `crop_x` 覆盖）。

### 步骤 5：生成字幕层

```bash
python scripts/make_captions.py config.json
```

字号按画幅自动计算（横屏会放大，避免手机上过小）。版式可用 `layout` 字段覆盖。

### 步骤 6：渲染母版

```bash
python scripts/render_master.py config.json
```

输出 `master_silent.mp4`（无音轨）。转场（默认 auto 自动选）+ 字幕叠加 + 画中画（若有）
+ 暗角（若有）+ 首尾淡入淡出。

渲染完**必须抽检**：每 4~6 秒抽一帧拼成图，确认字幕位置、转场、画中画、构图都对。

### 步骤 7：挑 BGM

```bash
python scripts/pick_bgm.py --list --category travel      # 列候选
python scripts/pick_bgm.py --pick "Just Keep Walking" "Summer Fun" --out-dir bgm
```

脚本从 Mixkit（**CC0，免费商用、无需署名**）抓曲目，下载后实测能量曲线并给出
推荐排序。判据是开头不空白 + 动态范围小。**按推荐结果选，别凭曲名感觉挑。**

把选定结果写进 config 的 `bgm` 字段。

### 步骤 8：混音

```bash
python scripts/mix_audio.py config.json
```

用 `-c:v copy` 直拷画面，秒出且画质零损失。脚本会自动检测响度并提示是否偏离
舒适区（纯 BGM 目标 -17~-18 LUFS），偏了就调 `volume_db` 重跑。

### 步骤 9：做封面

```bash
python scripts/make_cover.py config.json --out cover.jpg
```

横屏默认 `left` 版式（左侧暗渐变 + 左对齐，避开画面中的人物），
竖屏默认 `bottom` 版式。封面底图取自已切好的片段，不回读 4K 源。

### 步骤 10：交付

用 `present_files` 给出成片与封面，并在回复里附上**绝对路径**。

用户要第二个画幅时：**另开 `widescreen/` 子目录**，复制 config 改 `variant` /
`out_w` / `out_h` 后重跑步骤 4~9，竖屏版原样保留不被覆盖。

### 步骤 11：出公众号 / 小红书文案 + 配图（可选，强烈推荐）

成片做好后，顺手产一套社媒文案和配图，形成「视频 + 图文」完整投放包。
配图**从成片抽帧**（真实、零成本、风格统一），文案由 agent 按 `references/social-copy.md`
两套不同语气各写一份。

**① 抽静帧（配图素材）**

```bash
python scripts/extract_stills.py <最终成片.mp4> --out <work>/stills --count 9
```

均匀抽 9 张高质量静帧，并拼一张 `stills_sheet.jpg` 供挑封面。**长片也安全**（逐点 `-ss` 快定位，不全解）。

**② 挑封面静帧**：读 `stills_sheet.jpg`（已压到可读尺寸），选主体最干净、最有「封面感」的一张，
记下它的路径（如 `stills/still_03.jpg`）。

**③ 拼社媒图**

```bash
python scripts/make_social_assets.py stills/still_03.jpg \
    --title "青岛｜千里海岸" --subtitle "一场雨天的山海漫游" \
    --font "<config.font>" --gold "<config.gold>" --out <work>/social
```

输出 `social/xhs_cover.jpg`（小红书 3:4 封面）+ `social/wechat_header.jpg`（公众号 2.35:1 头图），
均带底部暗渐变 + 标题/金色副标题，手机可读。

**④ 写文案**（agent 执行，不要脚本代写）：按 `references/social-copy.md` 的模板，
读成片的 `captions[]` 叙事线，产出两个 `.md`：
- `social/wechat_article.md` —— 公众号长文（深度/故事/温度，800~1500 字）
- `social/xhs_post.md` —— 小红书笔记（口语/emoji/清单，含 3~6 个 #话题）

两套语气不同（见模板对照表），别同一段话改个标题就发两平台。`cover.line1/line2`
可直接当副标题母本，字幕【金色词】当金句/标签。

**⑤ 交付**：把 `social/` 三个文件 + 两个 `.md` 与成片一起 `present_files` 给出。

> config 可加可选 `social` 块预填文案母本，免去每次手敲：
> ```json
> "social": {
>   "title": "青岛｜千里海岸",
>   "subtitle": "一场雨天的山海漫游",
>   "cover_still": "stills/still_03.jpg",
>   "platforms": ["wechat", "xhs"],
>   "still_count": 9
> }
> ```
> 其中 `cover_still` 若省略，agent 读 sheet 自己挑最佳帧；`title` 缺省回落到视频 `title.main`。

## 关键提醒

- **字幕文案必须看图后写**，B-roll 素材无人声，语音识别只会返回空
- **裁切位置必须逐段核对**，居中裁切经常切掉人物半张脸
- **响度靠实测**，不要凭 dB 数值猜；低于 -20 LUFS 平台会二次增益导致削波
- **封面必须手动设**，平台自动截帧常抓到路人脸

完整避坑清单见 `references/pitfalls.md`，
平台规格与目录约定见 `references/platform-specs.md`，
字幕文案写法见 `references/caption-writing.md`。

## Resources

### scripts/

| 脚本 | 步骤 | 用途 |
|---|---|---|
| `check_env.py` | 0 | **环境自检**：ffmpeg/滤镜/Pillow/字体，缺啥给安装命令 |
| `probe_footage.py` | 1 | 探测素材规格，输出表格与总量评估 |
| `contact_sheet.py` | 2 | 抽帧拼图；可叠加裁切窗口验证主体 |
| `cut_clips.py` | 4 | 裁切/缩放素材到片段（支持 `kenburns` 关键帧推拉） |
| `make_captions.py` | 5 | PIL 渲染透明字幕层 PNG |
| `render_master.py` | 6 | 自动转场 + 字幕叠加 + 画中画 + 暗角，输出无音轨母版 |
| `pick_bgm.py` | 7 | 抓 Mixkit CC0 候选、实测能量曲线、推荐 |
| `mix_audio.py` | 8 | 混 BGM + 响度校准 + 检测 |
| `make_cover.py` | 9 | 生成封面（left / bottom 两种版式） |
| `extract_stills.py` | 11 | 从成片抽静帧 + 封面候选拼图（社媒配图素材） |
| `make_social_assets.py` | 11 | PIL 拼小红书封面(3:4) + 公众号头图(2.35:1) |

所有脚本用 `python3 <script> --help` 或看文件头部的 docstring 查参数。

### references/

- `setup.md` — **依赖安装手册**（macOS / Linux / Windows，含自检与常见问题）
- `pitfalls.md` — 8 条实测避坑（字幕滤镜缺失、横屏字号、裁切切人、码率、响度…）
- `ffmpeg-with-libass.md` — 从源码构建带 libass/freetype 的 ffmpeg（macOS 完整配方 + 踩坑）
- `platform-specs.md` — 视频号/抖音规格、画幅取舍、交付目录约定
- `caption-writing.md` — 字幕文案写法、结构模板、时间轴排布
- `social-copy.md` — 公众号长文 + 小红书笔记双模板、语气差异、配图布局、主题提炼

### assets/

- `project_config.example.json` — 项目配置模板（含完整的青岛啤酒博物馆实例）

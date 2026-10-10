# footage-to-short-video

把一批原始视频素材（DJI 无人机、相机、手机拍的旅拍 / 活动 / 探店 B-roll）剪成可直接发布的短视频：
裁切画幅 → 生成中文字幕 → 配 BGM → 做封面 → 校准码率与响度，输出竖屏 9:16 与横屏 16:9 双版本。

全流程本地完成，**不依赖剪映等 GUI 软件，不需要任何 API Key**。

这是一个 [WorkBuddy](https://www.workbuddy.cn) Skill，也可以当作独立的命令行工具链使用。

## 它能做什么

给一段素材目录，得到一条 60 秒成片 + 封面，具体包含：

- 素材规格探测、抽帧拼图（可叠加裁切窗口预览）
- 画幅转换（4K 横屏 → 9:16 竖屏时保证主体不被切掉）
- PIL 渲染的中文字幕层（圆角底条 + 金色关键词高亮 + 顶部渐变压暗）
- 交叉溶解转场、首尾淡入淡出
- 从 Mixkit（CC0，可商用免署名）挑 BGM，并按能量曲线自动推荐
- 混音 + 响度校准（防止平台二次增益削波）
- 封面生成（横屏走左侧版式避开人物）

## 快速开始

```bash
# 1. 环境自检（缺什么会直接给安装命令）
python3 skills-footage-to-short-video/scripts/check_env.py

# 2. 复制配置模板并改写
cp skills-footage-to-short-video/assets/project_config.example.json my_config.json

# 3. 按步骤跑
python3 skills-footage-to-short-video/scripts/probe_footage.py <素材目录> --ext .MP4
python3 skills-footage-to-short-video/scripts/contact_sheet.py <素材目录> --out sheet.jpg --per 3
python3 skills-footage-to-short-video/scripts/cut_clips.py my_config.json
python3 skills-footage-to-short-video/scripts/make_captions.py my_config.json
python3 skills-footage-to-short-video/scripts/render_master.py my_config.json
python3 skills-footage-to-short-video/scripts/pick_bgm.py --list --category travel
python3 skills-footage-to-short-video/scripts/mix_audio.py my_config.json
python3 skills-footage-to-short-video/scripts/make_cover.py my_config.json --out cover.jpg
```

每个脚本都有 `--help`，参数说明也写在文件头部 docstring 里。

## 依赖

只有三样：**ffmpeg / ffprobe**、**Python 3.9+**、**Pillow**，外加一款中文字体。
其余全部用标准库实现，**不依赖 numpy**（音频响度分析用 `array` + `math` 手算）。

各平台的完整安装步骤见 [`skills-footage-to-short-video/references/setup.md`](skills-footage-to-short-video/references/setup.md)。

> brew 装的 ffmpeg 是精简版，不含 libass/freetype，`subtitles` / `ass` / `drawtext` 三个滤镜不存在。
> 这不影响出片（本工具用 PIL 渲染字幕），只有在做「几十上百条对话字幕」时才需要补，
> 构建方法见 [`ffmpeg-with-libass.md`](skills-footage-to-short-video/references/ffmpeg-with-libass.md)。

## 目录结构

```
skills-footage-to-short-video/
├── SKILL.md                      # Skill 主文档（工作流 10 步）
├── scripts/
│   ├── check_env.py              # 环境自检
│   ├── probe_footage.py          # 1. 探测素材
│   ├── contact_sheet.py          # 2. 抽帧 + 裁切窗口预览
│   ├── cut_clips.py              # 4. 裁切画幅
│   ├── make_captions.py          # 5. PIL 渲染字幕层
│   ├── render_master.py          # 6. 转场 + 叠加 → 无音轨母版
│   ├── pick_bgm.py               # 7. 抓 CC0 曲库 + 能量曲线推荐
│   ├── mix_audio.py              # 8. 混音 + 响度校准
│   └── make_cover.py             # 9. 封面
├── references/
│   ├── setup.md                  # 依赖安装手册（三平台）
│   ├── pitfalls.md               # 8 条实测避坑
│   ├── ffmpeg-with-libass.md     # 自建带 libass 的 ffmpeg
│   ├── platform-specs.md         # 视频号/抖音规格与目录约定
│   └── caption-writing.md        # 字幕文案写法
└── assets/
    └── project_config.example.json   # 配置模板（含完整实例）
docs/
└── 交付清单-青岛啤酒博物馆.md     # 一次完整实战的产物与参数记录
```

所有决策集中在一个 `config.json` 里（每段素材的起止时间与裁切位置、字幕时间轴与文案、封面、BGM 音量），
脚本只读配置，换项目只需改这一个文件。

## 实例：青岛啤酒博物馆

7 段 DJI 4K 横屏素材 → 60 秒视频号短视频（竖屏 + 横屏双版本）。
完整的时间轴、字幕文案、BGM 选曲依据、两次返工记录（码率、响度）都在
[`docs/交付清单-青岛啤酒博物馆.md`](docs/交付清单-青岛啤酒博物馆.md)。

## 设计取舍

| 决策 | 原因 |
|---|---|
| 字幕用 PIL 渲染而非 ASS | 不依赖 ffmpeg 编译选项，圆角底条/局部高亮/渐变压暗都能精确控制 |
| 不引入 numpy | 受限环境下 pip 装 numpy 会 SIGTERM，标准库完全够用 |
| 母版与终版分离 | 换 BGM 时用 `-c:v copy` 直拷画面重混，不二次压缩 |
| 时间轴写在 config 而非命令行 | 双画幅版本共用同一套时间轴，改版不丢节奏 |

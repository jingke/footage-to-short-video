# 避坑手册（全部来自实测）

## 1. ffmpeg 没有字幕滤镜（最高频）

**现象**：`ffmpeg -filters` 里找不到 `subtitles` / `ass` / `drawtext`，报
`No such filter: 'subtitles'`。

**原因**：大量 brew/apt 安装的 ffmpeg 未编译 `--enable-libass` 与 `--enable-libfreetype`。

**检测**：
```bash
ffmpeg -hide_banner -h filter=subtitles 2>&1 | head -3
ffmpeg -hide_banner -buildconf 2>&1 | grep -iE "libass|libfreetype|fontconfig"
```

**方案 A — PIL 渲染透明字幕层（万能，跨平台）**：用 PIL 生成 RGBA 透明 PNG，再用 `overlay` 叠加。
- 优点：不依赖任何 ffmpeg 编译选项；圆角底条、顶部渐变压暗、关键词高亮、投影都能做
- 要点：PNG 必须是 RGBA 透明底；用 `-loop 1 -t <时长>` 把静图变成视频流
- 适合：**少量精致的文字卡**（本 skill 默认走这条路）

**方案 B — 自建带 libass 的 ffmpeg**：见 `references/ffmpeg-with-libass.md`（已在本机构建完成）。
- 适合：**几十上百条对话级字幕**，一个字幕文件管全片的场景
- 本机路径：`~/.workbuddy/bin/ffmpeg`，用法 `ffmpeg -vf "ass=sub.ass"`
- ⚠️ 它**不是系统 ffmpeg 的超集**（缺 libvpx/x265/dav1d 等外部库），别替换 PATH 里的默认 ffmpeg

## 2. 横屏字幕字号必须放大

同一套字号在两种画幅下观感差异巨大：

| 画幅 | 宽度 | 字号 | 占比 | 观感 |
|---|---|---|---|---|
| 竖屏 9:16 | 1080 | 52 | 4.8% | 正常 |
| 横屏 16:9 | 1920 | 56 | **2.9%** | ❌ 手机上偏小 |
| 横屏 16:9 | 1920 | 76 | 4.0% | ✅ 正常 |

经验公式：`cap_size ≈ out_w × 0.040`（横屏）/ `out_w × 0.048`（竖屏）
标题：`title_size ≈ out_h × 0.085`（横屏）/ `out_h × 0.048`（竖屏）

## 3. 竖屏裁切会切掉主体

横屏素材转 9:16 时，默认的居中裁切常常把人物切掉一半（尤其是主体偏一侧的镜头）。

**必须在切片段之前**，用 `contact_sheet.py --crop 9:16 --crop-x 1100 1312 1500`
在原始画面上画出候选裁切窗口，肉眼确认后再写入 config 的 `crop_x`。

不要只看小图目测 —— 直接对渲染好的母版密集抽帧（`每 4 秒一帧`）核对一次更准。

## 4. 码率过大

第一版容易出 14.9 Mbps / 112MB（4K 素材下采样后细节多）。短视频平台 1080p 的甜点是
**8 Mbps**。用 `-maxrate 8M -bufsize 16M -crf 21` 控制。

## 5. BGM 响度压太狠

把 BGM 按"背景音"直觉压到 -7dB，测出来只有 **-23.9 LUFS**，偏低。
平台上传后会做二次增益（通常归一化到 -14 LUFS 左右），把 -23.9 抬高约 10dB 时
true peak 会冲破 0 dBFS 造成削波。

**目标**：纯 BGM 无人声 → **-17 ~ -18 LUFS**；有人声 → -14 ~ -16 LUFS。
先把 BGM 混完再 `loudnorm=print_format=summary` 实测，别凭 dB 数值猜。

## 6. BGM 开头是空白

很多"大气""电影感"的曲子前 10~16 秒是缓慢渐入甚至近乎无声。
如果成片 1 秒内就出标题，片头会发闷。

**必须用 `pick_bgm.py` 实测开头 3 秒能量**：低于 -35dB 的直接弃用。

## 7. 素材无人声时不要做语音识别字幕

无人机/手持 B-roll 通常没有人说话，跑 Whisper 只会返回空。
这类素材的字幕应该是**场景说明文字卡**，文案靠抽帧看清画面后人工写。

## 8. 平台自动截帧会毁封面

上传后如果不手动设封面，平台自动截帧经常抓到路人脸、闭眼瞬间或过曝画面。
务必单独做封面图并在发布时手动指定。

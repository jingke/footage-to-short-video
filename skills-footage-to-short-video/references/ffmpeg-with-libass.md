# 自建一个带 libass / libfreetype 的 ffmpeg（macOS 实战记录）

## 为什么需要

homebrew 核心配方 `ffmpeg` 是**精简版**：只有 11 个依赖，**不编译 libass / libfreetype / fontconfig / harfbuzz / fribidi**，
因此 `subtitles`、`ass`、`drawtext` 三个滤镜都不存在。

官方替代是 `ffmpeg-full`（47 依赖，含上述全部），但在**受限沙箱环境里装不上**：
brew 倒 bottle 时要跑 `sandbox_operation.rb`，而嵌套 `sandbox-exec` 被拒，
报 `sandbox-exec: sandbox_apply: Operation not permitted`。
这跟用户权限无关（手工 `rm` 能删、`sandbox-exec` 单独跑也正常），是 brew 自身调用被拦。

自建是目前最稳的路子，全程只写用户目录、不动系统 ffmpeg。

## 前提：先装库（brew 装这些是正常的，失败的是 ffmpeg-full 本体）

```bash
brew install libass freetype fontconfig harfbuzz fribidi
```

## 步骤 1：pkg-config（ffmpeg configure 必需）

⚠️ `pkg-config 0.29.2`（2017 年最后版本）的内置 glib 编不过新版 clang：

```
./gatomic.h:191: error: __sync_fetch_and_or ... 4 errors generated.
```

改用 **pkgconf 1.7.4**（最后一个 autotools 版）：

```bash
cd /tmp && curl -sLO https://distfiles.dereferenced.org/pkgconf/pkgconf-1.7.4.tar.xz
tar xf pkgconf-1.7.4.tar.xz && cd pkgconf-1.7.4
./configure --prefix="$HOME/.workbuddy/pkgconfig" && make -j8 && make install
ln -sf pkgconf "$HOME/.workbuddy/pkgconfig/bin/pkg-config"
```

### 给 macOS 系统库补 .pc 文件

zlib / bzip2 / expat 在 macOS 上由 SDK 提供，没有 `.pc`，会导致
`Package 'zlib', required by 'freetype2', not found`。
自建三个最小 .pc 放进 `~/.workbuddy/pkgconfig/lib/pkgconfig/`：

```
# zlib.pc
prefix=/usr
exec_prefix=${prefix}
libdir=${prefix}/lib
includedir=${prefix}/include

Name: zlib
Description: zlib compression library (macOS SDK)
Version: 1.2.12
Libs: -lz
Cflags:
```

`bzip2.pc`（`Libs: -lbz2`）、`expat.pc`（`Libs: -lexpat`）同理。已验证 `clang -lz -lbz2 -lexpat` 能直接链接。

### 组装 PKG_CONFIG_PATH

所有 brew keg 的 pkgconfig 目录都要加，否则 keg-only 的库（libpng、graphite2、brotli、glib…）找不到：

```bash
export PKG_CONFIG_PATH="$HOME/.workbuddy/pkgconfig/lib/pkgconfig:$(ls -d /opt/homebrew/opt/*/lib/pkgconfig /opt/homebrew/opt/*/share/pkgconfig /opt/homebrew/lib/pkgconfig /opt/homebrew/share/pkgconfig 2>/dev/null | tr '\n' ':')"
```

## 步骤 2：configure + 编译

```bash
curl -sLO https://ffmpeg.org/releases/ffmpeg-8.1.1.tar.xz && tar xf ffmpeg-8.1.1.tar.xz
cd ffmpeg-8.1.1
export PATH="$HOME/.workbuddy/pkgconfig/bin:$PATH"
./configure --prefix="$HOME/.workbuddy/ffmpeg" \
  --pkg-config="$HOME/.workbuddy/pkgconfig/bin/pkg-config" \
  --enable-gpl --enable-version3 --enable-libx264 \
  --enable-libass --enable-libfreetype --enable-libfontconfig \
  --enable-libfribidi --enable-libharfbuzz \
  --disable-doc --disable-debug
make -j"$(sysctl -n hw.ncpu)" && make install
```

**两个必踩的坑**：

| 现象 | 原因 | 处理 |
|---|---|---|
| `ERROR: libmp3lame >= 3.98.3 not found` | brew 的 lame 没提供 .pc | 去掉 `--enable-libmp3lame`（AAC 用 ffmpeg 内置编码器就够） |
| `No such filter: 'drawtext'` | **drawtext 依赖 `libfreetype libharfbuzz` 两个都要** | 必须加 `--enable-libharfbuzz` |

编译很快，Apple Silicon 上 **约 2 分钟**。

## 步骤 3：验证

```bash
FF="$HOME/.workbuddy/ffmpeg/bin/ffmpeg"
$FF -hide_banner -buildconf | grep -iE "libass|freetype|fontconfig|fribidi|harfbuzz"
$FF -hide_banner -filters | grep -iE " (drawtext|ass|subtitles) "
```

三种烧字幕方式都已实测（中文渲染正常，无豆腐块）：

```bash
# SRT / 内嵌样式字幕
$FF -i in.mp4 -vf "subtitles=sub.srt" -c:v libx264 -crf 20 out.mp4
# ASS（可做关键词变色：{\c&H4EBEF0&}金色\c&HFFFFFF&白字）
$FF -i in.mp4 -vf "ass=sub.ass" -c:v libx264 -crf 20 out.mp4
# drawtext（临时叠字）
$FF -i in.mp4 -vf "drawtext=fontfile='/System/Library/Fonts/STHeiti Medium.ttc':text='青岛啤酒博物馆':fontsize=72:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2" out.mp4
```

字体由 fontconfig 解析，`STHeiti` / `Songti` 等系统字体直接可用，不必指定 fontfile。

## ⚠️ 不要直接替换系统 ffmpeg

自建版**不是超集**：它只有 x264 + ffmpeg 内置编解码器，
**没有** brew 版的 libvpx / x265 / dav1d / svt-av1 / lame / opus / openssl / libvmaf 等外部库。
把 `~/.workbuddy/bin` 加到 PATH 前面会让依赖 `libx265`、`libvpx-vp9` 的既有流程失效。

**正确用法**：默认仍用系统 ffmpeg；需要 libass 时显式指定路径，或临时前置：

```bash
export PATH="$HOME/.workbuddy/bin:$PATH"   # ~/.workbuddy/bin/ffmpeg 是自建版的软链
```

## 体积与路径

| 项 | 值 |
|---|---|
| 安装位置 | `~/.workbuddy/ffmpeg/`（97M） |
| 便捷软链 | `~/.workbuddy/bin/ffmpeg`、`~/.workbuddy/bin/ffprobe` |
| 版本 | ffmpeg 8.1.1（GPL v3，x264 + libass + freetype + fontconfig + fribidi + harfbuzz） |

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 v002 实验全景关系图（figures/01-experiment-landscape.png）。

设计意图：让外部读者一眼看到五组实验在生产链上的位置、样本量，以及
"哪些可以横比、哪些不能"。刻意不把跨任务数字并排画成同一根坐标轴。

依赖：Pillow（本地 11.3.0 可用）。字体用 macOS 自带 Hiragino Sans GB。
    python3 build_landscape.py            # 输出到 ./figures/
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1440, 1160
PAPER = (246, 244, 239)
INK = (32, 42, 44)
MUTED = (101, 113, 116)
LINE = (217, 221, 213)
ACCENT = (23, 120, 111)
PALE = (230, 240, 234)
GOLD = (191, 116, 54)
WARN = (163, 58, 46)
WHITE = (255, 255, 255)

REG_CANDIDATES = [
    ("/System/Library/Fonts/Hiragino Sans GB.ttc", 0),
    ("/System/Library/Fonts/STHeiti Light.ttc", 0),
    ("/System/Library/Fonts/Songti.ttc", 0),
]
BOLD_CANDIDATES = [
    ("/System/Library/Fonts/Hiragino Sans GB.ttc", 1),
    ("/System/Library/Fonts/STHeiti Medium.ttc", 0),
    ("/System/Library/Fonts/Songti.ttc", 1),
]


def load(candidates, size):
    for path, index in candidates:
        try:
            return ImageFont.truetype(path, size, index=index)
        except Exception:
            continue
    raise SystemExit("找不到可用的中文字体")


F_TITLE = load(BOLD_CANDIDATES, 38)
F_SUB = load(REG_CANDIDATES, 18)
F_CHAIN = load(BOLD_CANDIDATES, 17)
F_PANEL = load(BOLD_CANDIDATES, 21)
F_NAME = load(BOLD_CANDIDATES, 20)
F_META = load(REG_CANDIDATES, 15)
F_BODY = load(REG_CANDIDATES, 16)
F_CHIP = load(BOLD_CANDIDATES, 14)
F_NOTE = load(REG_CANDIDATES, 16)

img = Image.new("RGB", (W, H), PAPER)
d = ImageDraw.Draw(img)


def wrap(text, font, max_width):
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        if font.getlength(cur + ch) <= max_width:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def text_block(x, y, text, font, fill, max_width, line_h=None):
    line_h = line_h or int(font.size * 1.45)
    for i, line in enumerate(wrap(text, font, max_width)):
        d.text((x, y + i * line_h), line, font=font, fill=fill)
    return y + len(wrap(text, font, max_width)) * line_h


def card(x, y, w, h, name, meta, n, result, strength, accent):
    d.rounded_rectangle([x, y, x + w, y + h], radius=12, fill=WHITE, outline=LINE, width=1)
    d.rounded_rectangle([x, y, x + w, y + 7], radius=4, fill=accent)
    pad = 20
    cy = y + pad + 6
    cy = text_block(x + pad, cy, name, F_NAME, INK, w - 2 * pad) + 4
    cy = text_block(x + pad, cy, meta, F_META, MUTED, w - 2 * pad) + 8
    cy = text_block(x + pad, cy, "样本量：" + n, F_META, INK, w - 2 * pad) + 4
    cy = text_block(x + pad, cy, result, F_BODY, INK, w - 2 * pad)
    # 结论强度标签统一贴卡片底部，避免长短不一的正文把标签挤得参差
    chip_text = "结论强度：" + strength
    tw = F_CHIP.getlength(chip_text) + 20
    chip_y = y + h - 44
    d.rounded_rectangle([x + pad, chip_y, x + pad + tw, chip_y + 28], radius=14,
                        fill=accent, outline=None)
    d.text((x + pad + 10, chip_y + 6), chip_text, font=F_CHIP, fill=WHITE)


# ---------- 标题 ----------
d.text((48, 34), "具身数据生产实验全景（2026-10）", font=F_TITLE, fill=INK)
text_block(48, 86, "六组实验都在同一台 RTX 5090、同一套数据生成器上完成，但机器人、任务和指标各不相同。",
           F_SUB, MUTED, W - 96)
text_block(48, 110, "只有第一、二组是同一任务内的配对对照；其余各组的数字不能互相横比，图中已按此分区。",
           F_SUB, MUTED, W - 96)

# ---------- 生产链 ----------
chain_y = 158
d.text((48, chain_y), "生产链：", font=F_CHAIN, fill=INK)
stages = ["生产吞吐", "耗时归因", "场景多样性", "规划器", "操作对象与观测"]
cx = 48 + F_CHAIN.getlength("生产链：") + 6
for i, s in enumerate(stages):
    tw = F_CHAIN.getlength(s) + 26
    d.rounded_rectangle([cx, chain_y - 5, cx + tw, chain_y + 30], radius=8, fill=PALE, outline=LINE)
    d.text((cx + 13, chain_y + 2), s, font=F_CHAIN, fill=ACCENT)
    cx += tw
    if i < len(stages) - 1:
        d.text((cx + 8, chain_y + 2), "→", font=F_CHAIN, fill=GOLD)
        cx += 30

# ---------- 面板 A ----------
pa_y = 206
d.text((48, pa_y), "① 同一任务内的配对对照 — 可以横比", font=F_PANEL, fill=ACCENT)
ax, ay, aw, ah = 48, pa_y + 36, 660, 214
card(ax, ay, aw, ah, "实验一 · 导出模式对照",
     "AutoData 数据生产 / OpenArm 方块抓放 · 8 个并行环境", "3 模式 × 24 次尝试（另一轮 4 配置 × 17 次）",
     "最终就绪吞吐 1.245 → 1.616 条/分（+29.8%）；严格物理终态 23/24（三模式同一失败样本）",
     "可断言", ACCENT)
card(ax + aw + 24, ay, aw, ah, "实验二 · 内部耗时配对",
     "同一任务 · 4 个并行环境 · 固定 seed", "8 组配对，动作数组逐组 SHA256 匹配",
     "execute 197.5 → 142.7 秒；导出与背压 58.4 → 3.6 秒；瓶颈转向渲染与相机",
     "可断言", ACCENT)

# ---------- 面板 B ----------
pb_y = 512
d.text((48, pb_y), "② 不同任务 / 机器人 / 指标 — 不可横比", font=F_PANEL, fill=GOLD)
bx, by, bw, bh = 48, pb_y + 36, 660, 208
card(bx, by, bw, bh, "实验三 · 域随机化（OpenArm）",
     "物体 XY 位姿随机化 · 4 环境 × 64 次 reset", "256 个位姿样本，9 项检查",
     "能按配置边界采样并按 seed 复现（x ±40 mm、y ±60 mm）；未跑轨迹生成与成功率",
     "仅观察", GOLD)
card(bx + bw + 24, by, bw, bh, "实验四 · G1 视觉随机化",
     "人形 G1 家庭场景 · 头部视觉候选数据", "7 次尝试（单因素各 1 次）",
     "6 成功 / 1 失败；纯视觉组合 928 帧、18.56 秒，头部图像 MAE 36.14/255",
     "仅观察（n=1）", GOLD)
card(bx, by + bh + 22, bw, bh, "实验五 · 规划器与避障（cuRobo）",
     "OpenArm 单臂 MVP / Franka 家庭餐桌避障", "MVP 每版 5 次；避障每格 3 个配对状态；v2 补跑 16 条",
     "MVP：v1 5/5、v2 4/5；有障碍：IK 0/3、cuRobo 3/3；v2 补跑严格末态 15/16",
     "n=3，不可外推", WARN)
card(bx + bw + 24, by + bh + 22, bw, bh, "实验六 · 操作对象与观测",
     "Franka 家庭餐桌 · 方块换成香蕉", "1 条示范轨迹 × 2 个采集配置",
     "950 帧 / 19 秒完成抓取放置；腕部力中位数 38.7–38.8 N，撤离后归零",
     "n=1，仅流程可行", WARN)

# ---------- 图例与脚注 ----------
ly = by + 2 * bh + 22 + 26
d.text((48, ly), "结论强度：", font=F_CHIP, fill=INK)
lx = 48 + F_CHIP.getlength("结论强度：")
for label, color in [("可断言（同任务配对，数字可靠）", ACCENT),
                     ("仅观察（样本量只能说明可行）", GOLD),
                     ("不可外推（n≤3，禁止写成成功率）", WARN)]:
    tw = F_CHIP.getlength(label) + 24
    d.rounded_rectangle([lx, ly - 4, lx + tw, ly + 26], radius=14, fill=color)
    d.text((lx + 12, ly + 2), label, font=F_CHIP, fill=WHITE)
    lx += tw + 16

text_block(48, ly + 48,
           "共同边界：目前没有一组实验达到可以估计成功率的样本量——最大的对照样本是 3 个固定初始状态；"
           "一次 8 环境、目标 100 条的生产运行因内存不足被 SIGKILL 终止，数据回读验收尚未完成。",
           F_NOTE, INK, W - 96)

out = Path(__file__).resolve().parent / "figures"
out.mkdir(parents=True, exist_ok=True)
path = out / "01-experiment-landscape.png"
img.save(path, "PNG", optimize=True)
print(f"wrote {path} ({path.stat().st_size} bytes)")

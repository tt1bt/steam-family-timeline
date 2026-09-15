# -*- coding: utf-8 -*-
"""生成 exe 图标：packaging/icon.ico

设计：Steam 深蓝底 + 蓝色播放三角 + 下方三个递减的白点（时间线）。
在 16px 下也能认出轮廓，所以图形要粗、元素要少。
画在 4 倍尺寸再下采样，边缘才平滑。
"""

import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "icon.ico")

S = 1024                      # 超采样画布
STEAM_DARK = (27, 40, 56, 255)     # #1b2838
STEAM_BLUE = (102, 192, 244, 255)  # #66c0f4
STEAM_MID = (42, 71, 94, 255)      # #2a475e


def make() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    pad = int(S * 0.03)
    radius = int(S * 0.23)
    d.rounded_rectangle([pad, pad, S - pad, S - pad], radius=radius,
                        fill=STEAM_DARK)

    # 内描边，让图标在深色背景上也立得住
    inset = int(S * 0.085)
    d.rounded_rectangle([inset, inset, S - inset, S - inset],
                        radius=int(radius * 0.82),
                        outline=STEAM_MID, width=int(S * 0.022))

    # 播放三角：略偏上，给下方的时间线留位置
    cx, cy = S * 0.5, S * 0.435
    w = S * 0.135          # 半宽
    h = S * 0.175          # 半高
    d.polygon([(cx - w * 0.72, cy - h), (cx - w * 0.72, cy + h),
               (cx + w * 1.18, cy)], fill=STEAM_BLUE)

    # 时间线：三个递减的白点
    y = S * 0.735
    dots = [(S * 0.325, S * 0.038, 255),
            (S * 0.500, S * 0.030, 210),
            (S * 0.675, S * 0.022, 160)]
    for dx, r, a in dots:
        d.ellipse([dx - r, y - r, dx + r, y + r], fill=(255, 255, 255, a))
    # 把点连成线
    d.line([(S * 0.325, y), (S * 0.675, y)],
           fill=(255, 255, 255, 90), width=int(S * 0.011))
    for dx, r, a in dots:
        d.ellipse([dx - r, y - r, dx + r, y + r], fill=(255, 255, 255, a))

    return img


if __name__ == "__main__":
    art = make().resize((256, 256), Image.LANCZOS)
    art.save(OUT, format="ICO",
             sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                    (64, 64), (128, 128), (256, 256)])
    print(f"已生成 {OUT}  ({os.path.getsize(OUT):,} B)")
    # 顺带存一份 png 方便预览
    art.save(os.path.join(HERE, "icon-preview.png"))
    print("预览图 packaging/icon-preview.png")

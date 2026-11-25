"""데일리 투두 앱 아이콘 생성기.

토스 블루 그라데이션(#3182F6 → #1B64DA) 위에 흰색 체크 한 획만 크게 그린다.
아이폰 홈 화면 60pt에서도 바로 알아볼 수 있도록 여백과 획 두께를 잡았다.
icon-512-maskable.png 는 안드로이드가 원형으로 잘라도 체크가 잘리지 않도록
같은 그림을 78% 크기로 줄여 놓은 판이다.

    python3 make_icons.py
"""
import os

from PIL import Image, ImageDraw

W = 1024
C1 = (49, 130, 246)    # #3182F6
C2 = (27, 100, 218)    # #1B64DA
WHITE = (255, 255, 255)
STROKE = 104
MASKABLE_SCALE = 0.78

HERE = os.path.dirname(os.path.abspath(__file__))

# 체크 모양 (1024 기준)
POINTS = [(288, 512), (448, 672), (736, 348)]


def gradient(size):
    small = 128
    g = Image.new('RGB', (small, small))
    px = g.load()
    for y in range(small):
        for x in range(small):
            t = (x + y) / (2 * (small - 1))
            px[x, y] = tuple(round(C1[i] + (C2[i] - C1[i]) * t) for i in range(3))
    return g.resize((size, size), Image.BICUBIC)


def check_layer(scale=1.0):
    """투명 레이어에 체크 한 획을 (가운데 기준) scale 배로 그린다."""
    layer = Image.new('RGBA', (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    def p(x, y):
        return (W / 2 + (x - W / 2) * scale, W / 2 + (y - W / 2) * scale)

    pts = [p(x, y) for x, y in POINTS]
    width = max(2, round(STROKE * scale))
    d.line(pts, fill=WHITE + (255,), width=width, joint='curve')
    # 끝을 둥글게
    r = width / 2
    for x, y in (pts[0], pts[-1]):
        d.ellipse((x - r, y - r, x + r, y + r), fill=WHITE + (255,))
    return layer


def compose(scale):
    img = gradient(W).convert('RGBA')
    img = Image.alpha_composite(img, check_layer(scale))
    return img


def main():
    full = compose(1.0)
    maskable = compose(MASKABLE_SCALE)

    targets = [
        ('icon-512.png', full, 512),
        ('icon-192.png', full, 192),
        ('icon-180.png', full, 180),
        ('apple-touch-icon.png', full, 180),
        ('icon-512-maskable.png', maskable, 512),
    ]
    for name, img, size in targets:
        out = img.convert('RGB').resize((size, size), Image.LANCZOS)
        out.save(os.path.join(HERE, name), optimize=True)
        print('wrote', name, size)


if __name__ == '__main__':
    main()

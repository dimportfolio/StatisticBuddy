"""Draws the StatisticBuddy profile picture / logo (packaging/avatar.png).

Run: python packaging/make_avatar.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SIZE = 1024
SCALE = 2          # draw at 2x and downsample for smooth edges
S = SIZE * SCALE
OUT = Path(__file__).with_name("avatar.png")


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def main():
    # Background: diagonal gradient, deep indigo -> teal.
    top, bottom = (49, 46, 129), (13, 148, 136)
    bg = Image.new("RGB", (S, S))
    px = bg.load()
    for y in range(S):
        for x in range(0, S, 4):
            c = lerp(top, bottom, (x + y) / (2 * S))
            for dx in range(4):
                px[x + dx, y] = c
    img = bg.convert("RGBA")

    # Soft glow behind the chart.
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((S * .18, S * .16, S * .82, S * .80), fill=(255, 255, 255, 40))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(S * .06)))

    d = ImageDraw.Draw(img)

    # Rising bar chart.
    base_y = S * .70
    bar_w = S * .105
    gap = S * .045
    heights = [.16, .25, .35, .47]
    x0 = S * .5 - (4 * bar_w + 3 * gap) / 2
    colors = [(255, 255, 255, 170), (255, 255, 255, 200), (255, 255, 255, 230), (253, 224, 71, 255)]
    tops = []
    for i, (h, col) in enumerate(zip(heights, colors)):
        bx = x0 + i * (bar_w + gap)
        d.rounded_rectangle((bx, base_y - S * h, bx + bar_w, base_y), radius=S * .02, fill=col)
        tops.append((bx + bar_w / 2, base_y - S * h))

    # Upward trend arrow over the bars.
    pts = [(x, y - S * .07) for x, y in tops]
    d.line(pts, fill=(253, 224, 71, 255), width=int(S * .028), joint="curve")
    for x, y in pts[:-1]:
        r = S * .022
        d.ellipse((x - r, y - r, x + r, y + r), fill=(253, 224, 71, 255))
    # Arrow head pointing up-right from the last point.
    ax, ay = pts[-1]
    a = S * .07
    d.polygon([(ax + a * .55, ay - a * .75), (ax - a * .45, ay - a * .35), (ax + a * .15, ay + a * .45)],
              fill=(253, 224, 71, 255))

    # Baseline.
    d.rounded_rectangle((x0 - S * .03, base_y + S * .02, x0 + 4 * bar_w + 3 * gap + S * .03, base_y + S * .045),
                        radius=S * .012, fill=(255, 255, 255, 220))

    # Wordmark.
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", int(S * .085))
    except OSError:
        font = ImageFont.load_default()
    text = "StatisticBuddy"
    tw = d.textlength(text, font=font)
    d.text(((S - tw) / 2, S * .79), text, font=font, fill=(255, 255, 255, 240))

    img = img.resize((SIZE, SIZE), Image.LANCZOS).convert("RGB")
    img.save(OUT, optimize=True)
    print("saved", OUT)


if __name__ == "__main__":
    main()

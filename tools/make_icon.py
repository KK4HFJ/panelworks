"""Draw the PanelWorks icon: a form window (blue title bar, dotted design grid,
a command button and a green status LED) - a design surface and a live panel.

  python tools/make_icon.py        (needs Pillow; only to rebuild the icon)

Writes panelworks/assets/panelworks.ico (16-256 px, small sizes simplified so
they stay crisp) and panelworks.png (256 px, used as the window icon).
"""
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "panelworks", "assets")

BLUE, BLUE_HI = (43, 79, 129, 255), (74, 116, 176, 255)
FRAME, FACE, EDGE = (52, 56, 62, 255), (236, 236, 236, 255), (190, 190, 190, 255)
DOT = (165, 170, 178, 255)
BTN, BTN_HI, BTN_LO = (214, 214, 214, 255), (255, 255, 255, 255), (120, 120, 120, 255)
LED, LED_RIM, LED_HI = (60, 200, 70, 255), (20, 110, 30, 255), (190, 255, 190, 255)
TEXT = (95, 100, 108, 255)


def draw(size):
    """Draw at 4x the target size, then shrink with a good filter."""
    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = s / 64.0                                    # design on a 64-unit grid
    small = size <= 24

    def R(x0, y0, x1, y1):
        return [round(x0 * u), round(y0 * u), round(x1 * u), round(y1 * u)]

    # window frame
    m = 2 if small else 3
    rad = (4 if small else 6) * u
    d.rounded_rectangle(R(m, m + 2, 64 - m, 62 - m), radius=rad, fill=FRAME)
    d.rounded_rectangle(R(m + 2, m + 4, 62 - m, 60 - m), radius=rad * 0.6, fill=FACE)
    # title bar
    tb = 17 if small else 15
    d.rounded_rectangle(R(m + 2, m + 4, 62 - m, m + 4 + tb), radius=rad * 0.6, fill=BLUE)
    d.rectangle(R(m + 2, m + 4 + tb - 4, 62 - m, m + 4 + tb), fill=BLUE)
    d.rectangle(R(m + 2, m + 4, 62 - m, m + 6), fill=BLUE_HI)
    if not small:                                   # tiny window buttons
        for i in range(3):
            cx = 52 - m - i * 6
            d.ellipse(R(cx - 2, m + 9, cx + 2, m + 13), fill=(220, 228, 240, 255))
    top = m + 4 + tb

    # design grid
    if size >= 48:
        step = 6
        for gx in range(m + 6, 62 - m - 1, step):
            for gy in range(top + 4, 60 - m - 1, step):
                d.ellipse(R(gx - 0.45, gy - 0.45, gx + 0.45, gy + 0.45), fill=DOT)

    # command button (raised, VB style)
    bx0, by0, bx1, by1 = (m + 6, 44, m + 34, 54) if not small else (m + 5, 42, m + 33, 54)
    d.rectangle(R(bx0, by0, bx1, by1), fill=BTN)
    lw = max(1, round(u * (1.2 if not small else 1.6)))
    d.line(R(bx0, by0, bx1, by0), fill=BTN_HI, width=lw)
    d.line(R(bx0, by0, bx0, by1), fill=BTN_HI, width=lw)
    d.line(R(bx0, by1, bx1, by1), fill=BTN_LO, width=lw)
    d.line(R(bx1, by0, bx1, by1), fill=BTN_LO, width=lw)
    if size >= 32:                                  # caption on the button
        d.rectangle(R(bx0 + 7, (by0 + by1) / 2 - 1, bx1 - 7, (by0 + by1) / 2 + 1), fill=TEXT)

    # label lines
    if size >= 32:
        d.rectangle(R(m + 6, top + 7, m + 30, top + 10), fill=TEXT)
        d.rectangle(R(m + 6, top + 14, m + 22, top + 17), fill=TEXT)

    # green LED
    cx, cy, r = (48, 40, 9) if not small else (47, 38, 11)
    d.ellipse(R(cx - r, cy - r, cx + r, cy + r), fill=LED_RIM)
    d.ellipse(R(cx - r + 2, cy - r + 2, cx + r - 2, cy + r - 2), fill=LED)
    d.ellipse(R(cx - r / 2 - 1, cy - r / 2 - 1, cx - 1, cy - 1), fill=LED_HI)

    # a dashed selection box around the button, like the designer
    if size >= 64:
        x0, y0, x1, y1 = bx0 - 2, by0 - 2, bx1 + 2, by1 + 2
        dash = 2
        for x in range(int(x0), int(x1), dash * 2):
            d.line(R(x, y0, min(x + dash, x1), y0), fill=BLUE, width=max(1, round(u * 0.6)))
            d.line(R(x, y1, min(x + dash, x1), y1), fill=BLUE, width=max(1, round(u * 0.6)))
        d.rectangle(R(x1 - 1.4, y1 - 1.4, x1 + 1.4, y1 + 1.4), fill=(0, 0, 0, 255))

    return img.resize((size, size), Image.LANCZOS)


def main():
    os.makedirs(OUT, exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [draw(n) for n in sizes]
    big = images[-1]
    big.save(os.path.join(OUT, "panelworks.ico"), sizes=[(n, n) for n in sizes],
             append_images=images[:-1])
    big.save(os.path.join(OUT, "panelworks.png"))
    # contact sheet for checking how every size reads
    sheet = Image.new("RGBA", (sum(sizes) + 10 * len(sizes) + 10, 276), (255, 255, 255, 255))
    x = 10
    for n, im in zip(sizes, images):
        sheet.paste(im, (x, 266 - n), im)
        x += n + 10
    sheet.save(os.path.join(HERE, "icon_sheet.png"))
    print("wrote", os.path.join(OUT, "panelworks.ico"), "and panelworks.png")


if __name__ == "__main__":
    main()

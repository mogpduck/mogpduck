#!/usr/bin/env python3
"""
Static neofetch-style GitHub profile card.

Run it once, commit the two SVGs, forget about it. No API calls, no token,
no scheduled workflow. Re-run whenever you want to change the content.

    python3 build_profile.py                      # rebuild SVGs from CONTENT
    python3 build_profile.py --image me.jpg       # convert a photo to ASCII, then rebuild
    python3 build_profile.py --image me.jpg --width 46 --invert
    python3 build_profile.py --image me.jpg --preview   # print art, don't write files

The ASCII art is cached in art.txt. Edit that file by hand any time; the
build reads it as-is unless you pass --image again.

Requires: Pillow (only for --image).  pip install pillow
"""

import argparse
import os
import sys

# ---------------------------------------------------------------------------
# CONTENT
# ---------------------------------------------------------------------------
# Two-item tuples are (label, value) rows. Use None for a blank spacer line,
# and a one-item string for a bare line with no value column.

HANDLE = "matt@github"          # the header line, neofetch style
ART_FILE = "art.txt"
INFO_WIDTH = 62                 # character width of the right-hand column

CONTENT = [
    ("OS", "TODO: Windows 11, macOS, Fedora"),
    ("Uptime", "TODO: 10 years, 4 months"),
    ("Host", "TODO: employer, or leave it off"),
    ("Kernel", "Governance, Risk, and Compliance"),
    ("Shell", "TODO: your daily driver terminal"),
    None,
    ("Focus.Primary", "GRC, Program Management"),
    ("Focus.Adjacent", "Security Operations, People Leadership"),
    ("Focus.Current", "Cloud Architecture (AWS, Azure)"),
    None,
    ("Research.Areas", "AI Persuasion Ethics, Moral Agency"),
    ("Research.Areas", "Human-Computer Interaction"),
    ("Research.Venues", "IEEE S&P, USENIX, CHI, SOUPS, CSCW"),
    None,
    ("Hobbies.Software", "RPCS3 Modding, Texture Work"),
    ("Hobbies.Other", "Fantasy Football, NCAA Dynasty"),
    None,
    ("Contact",),
    ("Email", "TODO"),
    ("LinkedIn", "TODO"),
    ("GitHub", "TODO"),
]

# ---------------------------------------------------------------------------
# THEMES
# ---------------------------------------------------------------------------

THEMES = {
    "dark_mode.svg": {
        "bg": "#1a1b27",
        "border": "#2c2f45",
        "art": "#b7c0d8",
        "key": "#79dafa",
        "dots": "#4a5169",
        "value": "#dbe3ef",
        "accent": "#f4d67a",
    },
    "light_mode.svg": {
        "bg": "#ffffff",
        "border": "#d8dee4",
        "art": "#57606a",
        "key": "#0550ae",
        "dots": "#afb8c1",
        "value": "#1f2328",
        "accent": "#953800",
    },
}

# ---------------------------------------------------------------------------
# GEOMETRY
# ---------------------------------------------------------------------------

FONT_STACK = ("'DejaVu Sans Mono','JetBrains Mono','SF Mono','Cascadia Mono',"
              "Consolas,'Liberation Mono',monospace")
FONT_SIZE = 12
CHAR_W = FONT_SIZE * 0.6023     # DejaVu Sans Mono advance width
LINE_H = 16
PAD_X = 22
PAD_Y = 26
GUTTER = 5                      # blank chars between art and info columns

RAMP_DARK = " .'`^\",:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"
RAMP_LIGHT = RAMP_DARK[::-1]


# ---------------------------------------------------------------------------
# IMAGE -> ASCII
# ---------------------------------------------------------------------------

def image_to_ascii(path, width=46, invert=False, contrast=1.0, gamma=1.0):
    """Convert an image to a block of ASCII text.

    width    number of characters across; 40-50 matches the reference layout
    invert   flip the ramp, for a light background or a dark subject
    contrast >1 pushes highlights and shadows apart
    gamma    <1 brightens midtones, >1 darkens them
    """
    from PIL import Image, ImageEnhance, ImageOps

    img = Image.open(path)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        flat = Image.new("RGBA", img.size, (255, 255, 255, 255))
        flat.alpha_composite(img)
        img = flat
    img = img.convert("L")

    img = ImageOps.autocontrast(img, cutoff=2)
    if contrast != 1.0:
        img = ImageEnhance.Contrast(img).enhance(contrast)

    # characters are roughly twice as tall as they are wide
    height = max(1, int(width * img.height / img.width * 0.5))
    img = img.resize((width, height), Image.LANCZOS)

    ramp = RAMP_LIGHT if invert else RAMP_DARK
    last = len(ramp) - 1
    rows = []
    px = img.load()
    for y in range(height):
        row = []
        for x in range(width):
            v = px[x, y] / 255.0
            if gamma != 1.0:
                v = v ** gamma
            row.append(ramp[min(last, int(v * last))])
        rows.append("".join(row).rstrip())
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# SVG
# ---------------------------------------------------------------------------

def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def leader(label, value, width):
    """Label, dot leader, right-aligned value, neofetch style."""
    left = f"- {label}: "
    gap = width - len(left) - len(value)
    if gap <= 2:
        return left, " " * max(gap, 1), value
    return left, " " + "." * (gap - 2) + " ", value


def build_svg(art_lines, theme_file, colors):
    art_w = max((len(l) for l in art_lines), default=0)
    cols = art_w + GUTTER + INFO_WIDTH
    rows = max(len(art_lines), len(CONTENT) + 3)

    w = int(PAD_X * 2 + (cols + 2) * CHAR_W)
    h = int(PAD_Y * 2 + rows * LINE_H)
    info_x = PAD_X + (art_w + GUTTER) * CHAR_W

    out = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" font-size="{FONT_SIZE}" '
        f'font-family="{FONT_STACK}">',
        "<style>",
        f"  text {{ font-family: {FONT_STACK}; white-space: pre; }}",
        f"  .art {{ fill: {colors['art']}; }}",
        f"  .k {{ fill: {colors['key']}; }}",
        f"  .d {{ fill: {colors['dots']}; }}",
        f"  .v {{ fill: {colors['value']}; }}",
        f"  .a {{ fill: {colors['accent']}; }}",
        "</style>",
        f'<rect width="{w}" height="{h}" rx="8" fill="{colors["bg"]}" '
        f'stroke="{colors["border"]}"/>',
    ]

    y = PAD_Y + LINE_H
    for line in art_lines:
        out.append(f'<text x="{PAD_X}" y="{y}" class="art" '
                   f'xml:space="preserve">{esc(line)}</text>')
        y += LINE_H

    y = PAD_Y + LINE_H
    header_rule = "-" * max(0, INFO_WIDTH - len(HANDLE) - 1)
    out.append(f'<text x="{info_x}" y="{y}" xml:space="preserve">'
               f'<tspan class="a">{esc(HANDLE)}</tspan>'
               f'<tspan class="d"> {header_rule}</tspan></text>')
    y += LINE_H

    for row in CONTENT:
        if row is None:
            y += LINE_H
            continue
        if len(row) == 1:
            out.append(f'<text x="{info_x}" y="{y}" class="k" '
                       f'xml:space="preserve">- {esc(row[0])}</text>')
        else:
            left, dots, value = leader(row[0], row[1], INFO_WIDTH)
            out.append(f'<text x="{info_x}" y="{y}" xml:space="preserve">'
                       f'<tspan class="k">{esc(left)}</tspan>'
                       f'<tspan class="d">{esc(dots)}</tspan>'
                       f'<tspan class="v">{esc(value)}</tspan></text>')
        y += LINE_H

    out.append("</svg>")
    with open(theme_file, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    return w, h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", help="source photo to convert to ASCII")
    ap.add_argument("--width", type=int, default=46, help="art width in characters")
    ap.add_argument("--invert", action="store_true", help="flip the brightness ramp")
    ap.add_argument("--contrast", type=float, default=1.0)
    ap.add_argument("--gamma", type=float, default=1.0)
    ap.add_argument("--preview", action="store_true", help="print art only")
    args = ap.parse_args()

    if args.image:
        art = image_to_ascii(args.image, args.width, args.invert,
                             args.contrast, args.gamma)
        if args.preview:
            print(art)
            return
        with open(ART_FILE, "w", encoding="utf-8") as f:
            f.write(art + "\n")
        print(f"wrote {ART_FILE} ({args.width} chars wide)")

    if not os.path.exists(ART_FILE):
        sys.exit(f"no {ART_FILE}; run again with --image PATH")

    with open(ART_FILE, encoding="utf-8") as f:
        art_lines = f.read().rstrip("\n").split("\n")

    for name, colors in THEMES.items():
        w, h = build_svg(art_lines, name, colors)
        print(f"wrote {name} ({w}x{h})")


if __name__ == "__main__":
    main()

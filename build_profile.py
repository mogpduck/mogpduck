#!/usr/bin/env python3
"""
Static neofetch-style GitHub profile card.

Run it when you want to change something, commit the two SVGs, done.
No token, no scheduled workflow, no API calls.

    python3 build_profile.py                          # rebuild from art.txt
    python3 build_profile.py --source photo.jpg       # start from an image
    python3 build_profile.py --source art_source.txt  # start from existing ASCII
    python3 build_profile.py --preview                # print art, write nothing

Why --source and art.txt are separate: the script decodes whatever you give it
back into a luminance map, then re-encodes it for the card. art.txt is the
cached result. Edit it by hand any time; the build reads it as-is.

Feed it a PNG with a transparent background. The alpha channel becomes blank
space, so the subject floats instead of sitting in a rectangle of background
texture. That single detail matters more than any of the tuning flags.

Requires: Pillow.  pip install pillow
"""

import argparse
import hashlib
import os
import re
import sys

# ---------------------------------------------------------------------------
# CONTENT
# ---------------------------------------------------------------------------
# (label, value) rows. None is a blank spacer. A one-item tuple is a bare
# heading with no value column.

HANDLE = "matt@github"
ART_FILE = "art.txt"
INFO_WIDTH = 62                  # minimum; the column grows to fit long values

CONTENT = (
    ("Name", "Matt"),
    ("Research.Areas", "Moral agency and responsibility in human-AI decision systems"),
    ("Research.Areas", "Ethics of AI and algorithmic decision-making"),
    ("Research.Areas", "Human-Computer Interaction"),
    ("Research.Areas", "Digital Abuse & Privacy"),
    ("Hobbies.Software", "Modding old video games, writing small utilities"),
    ("Hobbies.Other", "Playing video games, mostly roguelikes and strategy games"),
)

# ---------------------------------------------------------------------------
# THEMES
# ---------------------------------------------------------------------------
# invert flips the ramp so a bright pixel becomes a dense glyph. That is the
# right call for a subject that is already light-on-dark, like a logo or line
# art. It is the wrong call for a photo of a person: dark hair is what carries
# the silhouette, and inverting hollows out the top of the head. Both themes
# therefore use the same polarity and differ only in colour.

THEMES = {
    "dark_mode.svg": {
        "invert": False,
        "bg": "#1a1b27",
        "border": "#2c2f45",
        "art": "#c3ccdf",
        "key": "#79dafa",
        "dots": "#4a5169",
        "value": "#dbe3ef",
        "accent": "#f4d67a",
    },
    "light_mode.svg": {
        "invert": False,
        "bg": "#ffffff",
        "border": "#d8dee4",
        "art": "#4a5058",
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
CHAR_W = FONT_SIZE * 0.6023      # DejaVu Sans Mono advance width
LINE_H = 16
PAD_X = 22
PAD_Y = 26
GUTTER = 5

OUT_RAMP = " .:-=+*#%@"          # sparse -> dense
CHAR_ASPECT = 0.5                # glyphs are about twice as tall as wide


# ---------------------------------------------------------------------------
# SOURCE -> LUMINANCE
# ---------------------------------------------------------------------------

def luma_from_image(path):
    """Return (grayscale, mask). mask is None unless the image has alpha.

    A transparent background is the single biggest quality win here: masked
    cells become blank space in both themes, so the subject floats instead of
    fighting a wall of background texture.
    """
    from PIL import Image, ImageOps
    img = Image.open(path)
    mask = None
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        alpha = img.getchannel("A")
        if alpha.getextrema()[0] < 250:
            mask = alpha
        flat = Image.new("RGBA", img.size, (255, 255, 255, 255))
        flat.alpha_composite(img)
        img = flat
    gray = img.convert("L")

    if mask is None:
        return ImageOps.autocontrast(gray, cutoff=2), None

    # stretch using the subject's own range; the cut-out background is pure
    # white and would otherwise pin the white point and flatten the face
    vals = sorted(v for v, m in zip(gray.tobytes(), mask.tobytes()) if m > 127)
    if len(vals) > 20:
        lo = vals[int(len(vals) * 0.02)]
        hi = vals[int(len(vals) * 0.98)]
        if hi > lo:
            scale = 255.0 / (hi - lo)
            gray = gray.point(
                lambda v: max(0, min(255, int((v - lo) * scale))))
    return gray, mask


def luma_from_ascii(path):
    """Decode an existing ASCII block back into a grayscale image.

    Infers the ramp from the characters present, ordered by ink density, and
    assumes the usual convention: dense glyph means dark pixel. Rows are
    stretched 2x vertically to undo the character aspect ratio.
    """
    from PIL import Image, ImageOps

    with open(path, encoding="utf-8") as f:
        lines = f.read().rstrip("\n").split("\n")
    width = max(len(l) for l in lines)
    lines = [l.ljust(width) for l in lines]

    density = (" .`'\",:;-_~^=+<>!|/\\)(][}{ijltfrxnvczJLYTCUIQOZ0mwqpdbkhao"
               "*3W#M%B8&@$")
    present = sorted(set("".join(lines)),
                     key=lambda c: density.index(c) if c in density
                     else len(density))
    if len(present) < 2:
        sys.exit(f"{path} has too few distinct characters to decode")
    step = 255 / (len(present) - 1)
    lut = {c: int(255 - i * step) for i, c in enumerate(present)}

    img = Image.new("L", (width, len(lines)))
    px = img.load()
    for y, row in enumerate(lines):
        for x, c in enumerate(row):
            px[x, y] = lut[c]
    img = img.resize((width, len(lines) * 2), Image.LANCZOS)
    return ImageOps.autocontrast(img, cutoff=1), None


def render_ascii(img, width, invert=False, contrast=1.0, gamma=1.0, mask=None):
    from PIL import Image, ImageEnhance

    if contrast != 1.0:
        img = ImageEnhance.Contrast(img).enhance(contrast)
    height = max(1, round(width * img.height / img.width * CHAR_ASPECT))
    img = img.resize((width, height), Image.LANCZOS)
    mpx = None
    if mask is not None:
        mpx = mask.resize((width, height), Image.LANCZOS).load()

    last = len(OUT_RAMP) - 1
    px = img.load()
    rows = []
    for y in range(height):
        row = []
        for x in range(width):
            if mpx is not None and mpx[x, y] < 128:
                row.append(' ')       # transparent -> blank
                continue
            v = px[x, y] / 255.0
            if not invert:
                v = 1.0 - v          # dark pixel -> dense glyph
            if gamma != 1.0:         # gamma > 1 thins the art out
                v = v ** gamma
            row.append(OUT_RAMP[min(last, int(v * last + 0.5))])
        rows.append("".join(row).rstrip())
    return "\n".join(rows)


def flip_ramp(art_lines):
    """Turn light-background art into dark-background art, glyph for glyph.

    Space is excluded from the flip. A blank cell is a hole in the cut-out
    mask, not a tone, so it has to stay blank in both themes. Flipping it
    would fill the whole background with the densest glyph.
    """
    width = max(len(l) for l in art_lines)
    tones = OUT_RAMP[1:]
    table = {c: tones[len(tones) - 1 - i] for i, c in enumerate(tones)}
    return ["".join(table.get(c, c) for c in line.ljust(width)).rstrip()
            for line in art_lines]


# ---------------------------------------------------------------------------
# SVG
# ---------------------------------------------------------------------------

def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text_el(x, y, chars, inner, cls=None):
    """One line of text, pinned to exactly len(chars) * CHAR_W.

    Without textLength the layout depends on the renderer picking a font whose
    advance width matches CHAR_W. Every common monospace face is close enough,
    but "close enough" over 140 columns is tens of pixels, and if the font runs
    wide the right-hand column overflows the viewBox and gets clipped.
    textLength makes the line occupy the width we budgeted no matter what font
    resolves; lengthAdjust="spacing" leaves the glyphs alone and absorbs the
    difference in the gaps, so the columns stay aligned.
    """
    klass = f' class="{cls}"' if cls else ""
    return (f'<text x="{x}" y="{y}"{klass} xml:space="preserve" '
            f'textLength="{len(chars) * CHAR_W:.2f}" lengthAdjust="spacing">'
            f'{inner}</text>')


def info_width():
    """Width of the right-hand column, in characters.

    INFO_WIDTH is a floor, not a ceiling. The column widens to fit the longest
    row so that a long value pushes the card out instead of running off the
    edge and getting clipped by the viewBox.
    """
    need = len(HANDLE) + 1
    for row in CONTENT:
        if row is None:
            continue
        if len(row) == 1:
            need = max(need, len(row[0]) + 2)
        else:
            need = max(need, len(f"- {row[0]}: ") + len(row[1]) + 1)
    return max(INFO_WIDTH, need)


def leader(label, value, width):
    left = f"- {label}: "
    gap = width - len(left) - len(value)
    if gap <= 2:
        return left, " " * max(gap, 1), value
    return left, " " + "." * (gap - 2) + " ", value


def build_svg(art_lines, filename, colors):
    art_w = max((len(l) for l in art_lines), default=0)
    info_rows = len(CONTENT) + 1
    iw = info_width()
    cols = art_w + GUTTER + iw
    rows = max(len(art_lines), info_rows)

    w = int(PAD_X * 2 + (cols + 2) * CHAR_W)
    h = int(PAD_Y * 2 + rows * LINE_H)
    info_x = PAD_X + (art_w + GUTTER) * CHAR_W
    # centre the shorter column against the taller one
    art_y0 = PAD_Y + LINE_H + max(0, (rows - len(art_lines)) // 2) * LINE_H
    info_y0 = PAD_Y + LINE_H + max(0, (rows - info_rows) // 2) * LINE_H

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

    y = art_y0
    for line in art_lines:
        if line.strip():
            out.append(text_el(PAD_X, y, line, esc(line), "art"))
        y += LINE_H

    y = info_y0
    rule = "-" * max(0, iw - len(HANDLE) - 1)
    header = f"{HANDLE} {rule}"
    out.append(text_el(info_x, y, header,
                       f'<tspan class="a">{esc(HANDLE)}</tspan>'
                       f'<tspan class="d"> {rule}</tspan>'))
    y += LINE_H

    for row in CONTENT:
        if row is None:
            y += LINE_H
            continue
        if len(row) == 1:
            out.append(text_el(info_x, y, f"- {row[0]}",
                               f"- {esc(row[0])}", "k"))
        else:
            left, dots, value = leader(row[0], row[1], iw)
            out.append(text_el(info_x, y, left + dots + value,
                               f'<tspan class="k">{esc(left)}</tspan>'
                               f'<tspan class="d">{esc(dots)}</tspan>'
                               f'<tspan class="v">{esc(value)}</tspan>'))
        y += LINE_H

    out.append("</svg>")
    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    return w, h


def stamp_readme(paths, path="README.md"):
    """Rewrite the ?v= cache buster on the image links in README.md.

    GitHub caches the rendered README server-side for a few minutes, so a
    hard refresh clears your browser but not theirs. A query string that
    changes with the file contents forces a fresh fetch on every push.
    """
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    for p in sorted(paths):
        with open(p, "rb") as f:
            h.update(f.read())
    tag = h.hexdigest()[:8]

    with open(path, encoding="utf-8") as f:
        text = f.read()
    new = re.sub(r"((?:dark|light)_mode\.svg)(\?v=[0-9a-f]+)?",
                 lambda m: f"{m.group(1)}?v={tag}", text)
    if new != text:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new)
    return tag


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", help="photo or existing ASCII file to convert")
    ap.add_argument("--width", type=int, default=50,
                    help="art width in characters")
    ap.add_argument("--crop",
                    help="LEFT,TOP,RIGHT,BOTTOM as fractions, e.g. .16,.02,.80,1")
    ap.add_argument("--contrast", type=float, default=1.0)
    ap.add_argument("--gamma", type=float, default=1.0)
    ap.add_argument("--preview", action="store_true",
                    help="print art, write nothing")
    args = ap.parse_args()

    if args.source:
        ext = os.path.splitext(args.source)[1].lower()
        img, mask = (luma_from_ascii(args.source) if ext in (".txt", ".text")
                     else luma_from_image(args.source))
        if args.crop:
            l, t, r, b = (float(v) for v in args.crop.split(","))
            box = (int(l * img.width), int(t * img.height),
                   int(r * img.width), int(b * img.height))
            img = img.crop(box)
            if mask is not None:
                mask = mask.crop(box)
        art = render_ascii(img, args.width, False, args.contrast,
                           args.gamma, mask)
        if args.preview:
            print(art)
            print(f"\n[{args.width} cols x {len(art.splitlines())} rows]")
            return
        with open(ART_FILE, "w", encoding="utf-8") as f:
            f.write(art + "\n")
        print(f"wrote {ART_FILE}")

    if not os.path.exists(ART_FILE):
        sys.exit(f"no {ART_FILE}; run again with --source PATH")

    with open(ART_FILE, encoding="utf-8") as f:
        light_art = f.read().rstrip("\n").split("\n")
    dark_art = flip_ramp(light_art)

    written = []
    for name, colors in THEMES.items():
        art = dark_art if colors["invert"] else light_art
        w, h = build_svg(art, name, colors)
        written.append(name)
        note = ("  <- wider than GitHub's column, it will scale down"
                if w > 1000 else "")
        print(f"wrote {name} ({w}x{h}){note}")

    tag = stamp_readme(written)
    if tag:
        print(f"stamped README.md with ?v={tag}")
    print("commit all three files, or GitHub keeps serving the old card")


if __name__ == "__main__":
    main()

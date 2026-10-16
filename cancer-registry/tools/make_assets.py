#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
توليد أصول الوحدة البصرية
==========================
    python3 tools/make_assets.py

يُنشئ:
  odoo/cancer_registry/static/description/icon.png     — 140×140 (أيقونة التطبيق)
  odoo/cancer_registry/static/description/banner.png   — 1200×400 (واجهة المتجر)
  README_assets/hero.png                               — غلاف التوثيق

الرسم برمجي بالكامل (Pillow) حتى تكون الأصول قابلة للتجديد بلا أدوات تصميم.
ملاحظة: Pillow لا يشكّل الحروف العربية، لذلك النصوص على الصور إنجليزية،
والتوثيق العربي في ملفات Markdown.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ADDON = ROOT / "odoo" / "cancer_registry"

NAVY_DARK = (12, 38, 66)
NAVY = (18, 58, 99)
NAVY_LIGHT = (28, 82, 138)
ACCENT = (97, 183, 255)
ACCENT_SOFT = (178, 218, 255)
WHITE = (255, 255, 255)
GREY = (226, 232, 240)
MUTED = (140, 158, 178)
GREEN = (46, 160, 96)
AMBER = (226, 168, 60)
RED = (200, 74, 66)

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
]
FONT_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
]


def font(size, bold=True):
    for path in (FONT_CANDIDATES if bold else FONT_REGULAR):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def vertical_gradient(size, top, bottom):
    w, h = size
    img = Image.new("RGB", size, top)
    px = img.load()
    for y in range(h):
        t = y / max(1, h - 1)
        px_row = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        for x in range(w):
            px[x, y] = px_row
    return img


def rounded(draw, box, radius, **kw):
    draw.rounded_rectangle(box, radius=radius, **kw)


# ═══════════════════════════════════════════════════════════════════════════
#  أيقونة التطبيق — 140×140
# ═══════════════════════════════════════════════════════════════════════════
def make_icon(path: Path, size=140):
    img = vertical_gradient((size, size), NAVY_LIGHT, NAVY_DARK).convert("RGBA")
    d = ImageDraw.Draw(img)

    # إطار مستدير
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size * 4, size * 4], radius=size * 4 * 0.22, fill=255)
    mask = mask.resize((size, size), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    d = ImageDraw.Draw(out)

    # ورقة السجل
    pad = size * 0.20
    sheet = [pad, pad * 0.86, size - pad * 1.28, size - pad * 0.86]
    rounded(d, sheet, size * 0.07, fill=WHITE)
    # رأس الورقة
    rounded(d, [sheet[0], sheet[1], sheet[2], sheet[1] + size * 0.15],
            size * 0.07, fill=ACCENT_SOFT)

    # أسطر البيانات
    x0 = sheet[0] + size * 0.06
    x1 = sheet[2] - size * 0.06
    y = sheet[1] + size * 0.23
    for i in range(4):
        w = x1 - (size * 0.14 if i % 2 else 0)
        rounded(d, [x0, y, w, y + size * 0.035], size * 0.018,
                fill=GREY if i else ACCENT)
        y += size * 0.105

    # عدسة التكبير (فحص الجودة)
    cx, cy, r = size * 0.715, size * 0.735, size * 0.155
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=ACCENT, width=max(3, size // 22))
    d.ellipse([cx - r * 0.55, cy - r * 0.55, cx + r * 0.55, cy + r * 0.55],
              outline=ACCENT, width=max(2, size // 34))
    hx, hy = cx + r * 0.78, cy + r * 0.78
    d.line([cx + r * 0.55, cy + r * 0.55, hx + size * 0.055, hy + size * 0.055],
           fill=ACCENT, width=max(4, size // 17))

    path.parent.mkdir(parents=True, exist_ok=True)
    out.convert("RGB").save(path, "PNG")
    return path


# ═══════════════════════════════════════════════════════════════════════════
#  واجهة المتجر — 1200×400
# ═══════════════════════════════════════════════════════════════════════════
def make_banner(path: Path, w=1200, h=400):
    img = vertical_gradient((w, h), NAVY_LIGHT, NAVY_DARK).convert("RGB")
    d = ImageDraw.Draw(img)

    # شبكة خفيفة في الخلفية
    for x in range(0, w, 40):
        d.line([x, 0, x, h], fill=(24, 68, 112), width=1)
    for y in range(0, h, 40):
        d.line([0, y, w, y], fill=(24, 68, 112), width=1)

    d.rectangle([0, 0, w, 6], fill=ACCENT)

    # ── اللوحة اليمنى: بطاقة سجل مصغّرة (تُرسم أولاً ليُحسب الفضاء المتاح) ──
    cx, cy, cw, ch = w - 352, 52, 296, 296
    rounded(d, [cx, cy, cx + cw, cy + ch], 14, fill=WHITE)
    rounded(d, [cx, cy, cx + cw, cy + 44], 14, fill=NAVY)
    d.rectangle([cx, cy + 22, cx + cw, cy + 44], fill=NAVY)
    d.text((cx + 16, cy + 12), "CR2026/0001", font=font(17), fill=WHITE)

    rows = [
        ("National ID", "119780445231"),
        ("Primary site", "C50.4  upper-outer quadrant"),
        ("Morphology", "8500/3  ductal carcinoma"),
        ("TNM / stage", "pT2 pN1 cM0  →  Stage IIB"),
        ("Quality score", "96 / 100   •  3 archived scans"),
    ]
    y = cy + 58
    for i, (label, value) in enumerate(rows):
        d.text((cx + 16, y), label, font=font(13, bold=False), fill=MUTED)
        d.text((cx + 16, y + 17), value, font=font(15),
               fill=GREEN if "96 /" in value else (28, 43, 58))
        if i < len(rows) - 1:
            d.line([cx + 16, y + 40, cx + cw - 16, y + 40],
                   fill=(238, 242, 247), width=1)
        y += 47

    # شريط ملوّن أسفل البطاقة
    d.rectangle([cx + 16, cy + ch - 14, cx + cw - 16, cy + ch - 8], fill=GREY)
    d.rectangle([cx + 16, cy + ch - 14, cx + 16 + (cw - 32) * 0.96, cy + ch - 8],
                fill=GREEN)

    limit = cx - 60                                   # أقصى عرض للنصوص اليسرى

    # ── العنوان ──
    d.text((56, 46), "Cancer Registry", font=font(56), fill=WHITE)
    d.text((56, 118),
           "National Cancer Registry  •  National Cancer Institute, Sabratha",
           font=font(18, bold=False), fill=ACCENT_SOFT)
    d.text((56, 148),
           "OCR extraction  •  ICD-O-3 coding  •  TNM staging  •  40+ QC rules",
           font=font(18, bold=False), fill=(200, 216, 234))

    # ── الأزرار الستة (تُلفّ إن تجاوزت الحد) ──
    labels = ["Upload scan", "Auto-extract", "Quality check",
              "Preview", "Storage", "Export"]
    f = font(16)
    x, y = 56, 206
    for lab in labels:
        tw = d.textlength(lab, font=f)
        bw = tw + 30
        if x + bw > limit:
            x, y = 56, y + 46
        rounded(d, [x, y, x + bw, y + 34], 17, fill=WHITE)
        d.text((x + 15, y + 8), lab, font=f, fill=NAVY)
        x += bw + 12

    # ── السطر الختامي ──
    d.text((56, 330),
           "One data dictionary  →  standalone desktop tool  +  Odoo 17/18 module",
           font=font(17, bold=False), fill=MUTED)

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG", optimize=True)
    return path


# ═══════════════════════════════════════════════════════════════════════════
#  غلاف التوثيق
# ═══════════════════════════════════════════════════════════════════════════
def make_hero(path: Path, w=1200, h=300):
    img = vertical_gradient((w, h), NAVY, NAVY_DARK).convert("RGB")
    d = ImageDraw.Draw(img)
    d.rectangle([0, h - 6, w, h], fill=ACCENT)

    d.text((56, 62), "Cancer Registry System", font=font(50), fill=WHITE)
    d.text((56, 132),
           "From scanned paper to a coded, audited national cancer registry",
           font=font(22, bold=False), fill=ACCENT_SOFT)

    steps = ["Scan", "OCR", "Extract", "Validate", "Export"]
    x, y = 56, 196
    for i, step in enumerate(steps):
        tw = d.textlength(step, font=font(18))
        rounded(d, [x, y, x + tw + 30, y + 38], 8, fill=NAVY_LIGHT)
        d.text((x + 15, y + 9), step, font=font(18), fill=WHITE)
        x += tw + 30
        if i < len(steps) - 1:
            d.text((x + 6, y + 9), "→", font=font(18), fill=ACCENT)
            x += 34

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG", optimize=True)
    return path


def main():
    targets = [
        (ADDON / "static" / "description" / "icon.png", make_icon),
        (ADDON / "static" / "description" / "banner.png", make_banner),
        (ROOT / "docs" / "hero.png", make_hero),
    ]
    for path, fn in targets:
        out = fn(path)
        size = out.stat().st_size
        with Image.open(out) as im:
            print("  ✓ %-58s %sx%s  %s ك.ب" % (
                out.relative_to(ROOT), im.width, im.height, round(size / 1024, 1)))


if __name__ == "__main__":
    main()

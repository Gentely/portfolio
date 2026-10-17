#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""بطاقات QR لصفحات الموقع — E-Gen + جوهرة (1080x1400). نسخة نهائية بتخطيط مقاس."""
from pathlib import Path

import arabic_reshaper
import qrcode
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from qrcode.constants import ERROR_CORRECT_M

BASE = Path(__file__).resolve().parent
FONTS = BASE.parent / "products" / "fonts"

NAVY_TOP, NAVY_BOT = (8, 15, 30), (13, 27, 51)
WHITE = (242, 246, 252)
MUTED = (159, 179, 200)
TEAL = (45, 212, 167)
GOLD = (227, 179, 65)
GOLD_DARK = (160, 118, 20)
NAVY_TEXT = (6, 20, 34)
QR_DARK = (10, 19, 36)

_reshaper = arabic_reshaper.ArabicReshaper(configuration={"support_ligatures": True})


def S(t):
    return get_display(_reshaper.reshape(str(t)), base_dir="R")


def font(size, bold=True):
    return ImageFont.truetype(str(FONTS / ("Amiri-Bold.ttf" if bold else "Amiri-Regular.ttf")), size)


def centered(d, cx, y, txt, fnt, fill):
    """يرسم النص متمركزاً بحيث y هي أعلى النص بصرياً، ويعيد ارتفاعه الحقيقي."""
    b = d.textbbox((0, 0), txt, font=fnt)
    w, h = b[2] - b[0], b[3] - b[1]
    d.text((cx - w / 2, y - b[1]), txt, font=fnt, fill=fill)
    return h


def measure(d, txt, fnt):
    b = d.textbbox((0, 0), txt, font=fnt)
    return b[3] - b[1]


def bg(w, h):
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(h - 1, 1)
        d.line([(0, y), (w, y)], fill=tuple(int(NAVY_TOP[i] + (NAVY_BOT[i] - NAVY_TOP[i]) * t) for i in range(3)))
    glow = Image.new("RGB", (w, h), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([w * 0.4, -h * 0.2, w * 1.3, h * 0.3], fill=(10, 60, 55))
    gd.ellipse([-w * 0.4, h * 0.6, w * 0.3, h * 1.2], fill=(8, 40, 60))
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    return Image.blend(img, Image.blend(img, glow, 0.55), 0.6)


def draw_gem(d, cx, cy, s):
    tl, tr = (cx - s, cy - s * 0.55), (cx + s, cy - s * 0.55)
    ml, mr = (cx - s * 1.15, cy - s * 0.05), (cx + s * 1.15, cy - s * 0.05)
    bot = (cx, cy + s * 0.95)
    sl, sr = (cx - s * 0.45, cy - s * 0.55), (cx + s * 0.45, cy - s * 0.55)
    d.polygon([tl, sl, ml], fill=(24, 90, 110))
    d.polygon([sl, sr, mr, ml], fill=(30, 130, 140))
    d.polygon([sr, tr, mr], fill=(24, 90, 110))
    d.polygon([ml, mr, bot], fill=(18, 70, 95))
    for a, b in [(tl, bot), (tr, bot), (sl, bot), (sr, bot)]:
        d.line([a, b], fill=GOLD, width=max(3, s // 14))
    d.polygon([tl, tr, mr, ml], outline=GOLD, width=max(3, s // 14))
    d.line([ml, mr], fill=GOLD, width=max(3, s // 14))


def make_qr(url, px):
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, border=2, box_size=10)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color=QR_DARK, back_color="white").convert("RGB")
    return img.resize((px, px), Image.NEAREST)


def card(filename, brand, brand_latin, subtitle, url, band_lines, band_h):
    W, H = 1080, 1400
    img = bg(W, H)
    d = ImageDraw.Draw(img)
    band_y = H - band_h

    draw_gem(d, W // 2, 132, 60)
    y = 208
    if brand_latin:
        y += centered(d, W // 2, y, brand_latin, font(78), TEAL) + 18
        y += centered(d, W // 2, y, S(brand), font(52), GOLD) + 22
    else:
        y += centered(d, W // 2, y, S(brand), font(84), GOLD) + 24
    y += centered(d, W // 2, y, S(subtitle), font(42, bold=False), MUTED) + 22

    # قياس سطرَي الأسفل لحجز مساحتهما قبل تحديد حجم اللوحة
    scan_f, url_f = font(42), font(30, bold=False)
    scan_txt, url_txt = S("امسح بكاميرا هاتفك للوصول مباشرة"), url.replace("https://", "")
    need_below = 22 + measure(d, scan_txt, scan_f) + 12 + measure(d, url_txt, url_f) + 18

    pad = 34
    qr_px = max(380, min(640, band_y - need_below - y - pad * 2))
    panel = qr_px + pad * 2
    x0 = (W - panel) // 2
    d.rounded_rectangle([x0, y, x0 + panel, y + panel], radius=36, fill=(255, 255, 255))
    img.paste(make_qr(url, qr_px), (x0 + pad, y + pad))
    y += panel + 22
    y += centered(d, W // 2, y, scan_txt, scan_f, WHITE) + 12
    centered(d, W // 2, y, url_txt, url_f, MUTED)

    # الشريط الذهبي: توسيط عمودي بالقياس الحقيقي
    d.rectangle([0, band_y, W, H], fill=GOLD)
    d.rectangle([0, band_y, W, band_y + 6], fill=GOLD_DARK)
    rendered = []
    total = 0
    for line, sz in band_lines:
        txt = "00218-918199601" if line == "WA_NUMBER" else S(line)
        f = font(sz)
        rendered.append((txt, f))
        total += measure(d, txt, f)
    total += 8 * (len(rendered) - 1)
    ly = band_y + (band_h - total) // 2
    for txt, f in rendered:
        ly += centered(d, W // 2, ly, txt, f, NAVY_TEXT) + 8

    path = BASE / filename
    img.save(path)
    print(path.name, path.stat().st_size)


if __name__ == "__main__":
    card(
        "qr-egen.png",
        brand="أدوات البريد المجانية",
        brand_latin="E-Gen",
        subtitle="بريد مؤقت بصندوق وارد + مولّد إيميلات وهمية",
        url="https://gentely.github.io/portfolio/tools/e-gen.html",
        band_lines=[("أدوات مجانية — تعمل بالكامل في متصفحك", 42)],
        band_h=120,
    )
    card(
        "qr-jawhara.png",
        brand="جوهرة",
        brand_latin=None,
        subtitle="حزمة تدقيق البيانات — فحص كامل بـ 24 بنداً",
        url="https://gentely.github.io/portfolio/landing/",
        band_lines=[("اطلبها الآن عبر واتساب — 20 دولاراً فقط", 40), ("WA_NUMBER", 42)],
        band_h=142,
    )
    print("QR OK")

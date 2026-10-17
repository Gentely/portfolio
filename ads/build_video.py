#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""فيديو إعلاني قصير لمنتج «جوهرة» — 35 ثانية، عمودي + مربع، بدون صوت (نصوص متحركة)."""
import math
import subprocess
from pathlib import Path

import arabic_reshaper
import imageio_ffmpeg
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFilter, ImageFont

BASE = Path(__file__).resolve().parent
FONTS = BASE.parent / "products" / "fonts"
FPS = 15
DUR = 35.0

NAVY_TOP, NAVY_BOT = (8, 15, 30), (13, 27, 51)
PANEL = (20, 38, 66, 255)
PANEL_LINE = (46, 74, 110, 255)
WHITE = (242, 246, 252)
MUTED = (159, 179, 200)
TEAL = (45, 212, 167)
GOLD = (227, 179, 65)
GOLD_RGB = (227, 179, 65)
GREEN = (52, 211, 153)
AMBER = (251, 191, 36)
RED = (248, 113, 113)
NAVY_TEXT = (6, 20, 34)

_reshaper = arabic_reshaper.ArabicReshaper(configuration={"support_ligatures": True})
_shape_cache, _font_cache = {}, {}


def S(t):
    if t not in _shape_cache:
        _shape_cache[t] = get_display(_reshaper.reshape(str(t)), base_dir="R")
    return _shape_cache[t]


def F(size, bold=True):
    key = (size, bold)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(
            str(FONTS / ("Amiri-Bold.ttf" if bold else "Amiri-Regular.ttf")), size)
    return _font_cache[key]


def ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def prog(t, start, dur=0.7):
    return ease((t - start) / dur)


def with_alpha(color, a):
    rgb = color[:3]
    return rgb + (int(255 * max(0.0, min(1.0, a))),)


def centered(d, cx, y, txt, fnt, fill):
    b = d.textbbox((0, 0), txt, font=fnt)
    w, h = b[2] - b[0], b[3] - b[1]
    d.text((cx - w / 2, y - b[1]), txt, font=fnt, fill=fill)
    return h


def right_text(d, xr, y, txt, fnt, fill):
    b = d.textbbox((0, 0), txt, font=fnt)
    d.text((xr - (b[2] - b[0]), y - b[1]), txt, font=fnt, fill=fill)
    return b[3] - b[1]


def make_bg(W, H):
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / max(H - 1, 1)
        d.line([(0, y), (W, y)], fill=tuple(int(NAVY_TOP[i] + (NAVY_BOT[i] - NAVY_TOP[i]) * t) for i in range(3)))
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W * 0.4, -H * 0.2, W * 1.3, H * 0.3], fill=(10, 60, 55))
    gd.ellipse([-W * 0.4, H * 0.6, W * 0.3, H * 1.2], fill=(8, 40, 60))
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    return Image.blend(img, Image.blend(img, glow, 0.55), 0.6).convert("RGBA")


def draw_gem(d, cx, cy, s, a=1.0, line=GOLD):
    tl, tr = (cx - s, cy - s * 0.55), (cx + s, cy - s * 0.55)
    ml, mr = (cx - s * 1.15, cy - s * 0.05), (cx + s * 1.15, cy - s * 0.05)
    bot = (cx, cy + s * 0.95)
    sl, sr = (cx - s * 0.45, cy - s * 0.55), (cx + s * 0.45, cy - s * 0.55)
    d.polygon([tl, sl, ml], fill=with_alpha((24, 90, 110), a))
    d.polygon([sl, sr, mr, ml], fill=with_alpha((30, 130, 140), a))
    d.polygon([sr, tr, mr], fill=with_alpha((24, 90, 110), a))
    d.polygon([ml, mr, bot], fill=with_alpha((18, 70, 95), a))
    wdt = max(3, s // 14)
    for p, q in [(tl, bot), (tr, bot), (sl, bot), (sr, bot)]:
        d.line([p, q], fill=with_alpha(line, a), width=wdt)
    d.polygon([tl, tr, mr, ml], outline=with_alpha(line, a), width=wdt)
    d.line([ml, mr], fill=with_alpha(line, a), width=wdt)


def draw_icon(d, cx, cy, r, kind, a=1.0):
    color = {"check": GREEN, "warn": AMBER, "x": RED}[kind]
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=with_alpha(color, a))
    w = max(4, r // 4)
    ink = with_alpha(NAVY_TEXT, a)
    if kind == "check":
        d.line([(cx - r * 0.5, cy), (cx - r * 0.12, cy + r * 0.42), (cx + r * 0.55, cy - r * 0.42)], fill=ink, width=w, joint="curve")
    elif kind == "x":
        d.line([(cx - r * 0.38, cy - r * 0.38), (cx + r * 0.38, cy + r * 0.38)], fill=ink, width=w)
        d.line([(cx + r * 0.38, cy - r * 0.38), (cx - r * 0.38, cy + r * 0.38)], fill=ink, width=w)
    else:
        d.rounded_rectangle([cx - w // 2, cy - r * 0.5, cx + w // 2, cy + r * 0.18], radius=w // 2, fill=ink)
        d.ellipse([cx - w // 2, cy + r * 0.32, cx + w // 2, cy + r * 0.32 + w], fill=ink)


def draw_sheet(d, x, y, w, icons, rh=84, a=1.0):
    rows = len(icons) + 1
    total_h = rh * rows
    d.rounded_rectangle([x, y, x + w, y + total_h], radius=22, fill=with_alpha(PANEL, a), outline=with_alpha(PANEL_LINE, a), width=3)
    d.rounded_rectangle([x, y, x + w, y + rh], radius=22, fill=with_alpha((28, 58, 92), a))
    d.rectangle([x, y + rh // 2, x + w, y + rh], fill=with_alpha((28, 58, 92), a))
    cols = [int(w * 0.16), int(w * 0.34), int(w * 0.28), int(w * 0.22)]
    for i in range(rows):
        ry = y + i * rh
        cx = x
        for j, cw in enumerate(cols):
            cx += cw
            if j < 3:
                d.line([(cx, ry + 10), (cx, ry + rh - 10)], fill=with_alpha(PANEL_LINE, a), width=2)
        if i > 0:
            d.line([(x + 8, ry), (x + w - 8, ry)], fill=with_alpha(PANEL_LINE, a), width=2)
            kind = icons[i - 1]
            if kind:
                draw_icon(d, x + w - 52, ry + rh // 2, 21, kind, a)
                for k, bw in enumerate([0.30, 0.20, 0.12]):
                    bx = x + 34 + int(k * w * 0.24)
                    d.rounded_rectangle([bx, ry + rh // 2 - 8, bx + int(w * bw * 0.55), ry + rh // 2 + 8],
                                        radius=8, fill=with_alpha((90, 120, 155), a))
    return total_h


def card_row(d, x, y, w, h, icon, title, sub, a=1.0, dy=0):
    y += dy
    d.rounded_rectangle([x, y, x + w, y + h], radius=20, fill=with_alpha(PANEL, a), outline=with_alpha(PANEL_LINE, a), width=2)
    draw_icon(d, x + w - 58, y + h // 2, 24, icon, a)
    right_text(d, x + w - 104, y + 22, S(title), F(44), with_alpha(WHITE, a))
    if sub:
        right_text(d, x + w - 104, y + 82, S(sub), F(34, bold=False), with_alpha(MUTED, a))


AXES = ["اكتمال البيانات", "الدقة والصحة", "التكرار والازدواج",
        "التنسيق والاتساق", "السلامة والمنطق", "التوثيق والقبول"]


def render_frame(W, H, t):
    img = make_bg(W, H)
    d = ImageDraw.Draw(img)
    cx = W // 2
    fy = lambda f: int(H * f)

    if t < 4.0:  # S1 الخطاف
        shake = int(math.sin(t * 40) * 8 * max(0.0, 1 - t / 0.7)) if t < 0.7 else 0
        draw_gem(d, cx, fy(0.155), 62, prog(t, 0.0, 0.6))
        a = prog(t, 0.3)
        centered(d, cx, fy(0.225), S("بياناتك فيها أخطاء؟"), F(92), with_alpha(WHITE, a))
        icons = []
        for i in range(5):
            icons.append("x" if t > 0.9 + i * 0.45 else None)
        draw_sheet(d, 90 + shake, fy(0.36), W - 180, icons, rh=int(H * 0.052), a=prog(t, 0.5))
        centered(d, cx, fy(0.36) + int(H * 0.052) * 6 + 44, S("أخطاء لا تراها… حتى تقع الخسارة"),
                 F(42, bold=False), with_alpha(MUTED, prog(t, 2.6)))

    elif t < 10.0:  # S2 الألم
        lt = t - 4.0
        centered(d, cx, fy(0.13), S("أخطاء صامتة… تكلّفك الكثير"), F(62), with_alpha(WHITE, prog(lt, 0)))
        pains = [("سجل مكرر", "دفعت المبلغ مرتين", "x"),
                 ("رقم هاتف ناقص", "خسرت عميلاً كان سيشتري", "x"),
                 ("مبلغ بصيغة خاطئة", "تقرير كامل أصبح باطلاً", "warn")]
        y = fy(0.27)
        for i, (ti, su, ic) in enumerate(pains):
            p = prog(lt, 0.5 + i * 1.5)
            card_row(d, 90, y, W - 180, int(H * 0.105), ic, ti, su, p, dy=int((1 - p) * 46))
            y += int(H * 0.105) + int(H * 0.022)
        centered(d, cx, y + 26, S("والحل أبسط مما تظن…"), F(44), with_alpha(TEAL, prog(lt, 5.0)))

    elif t < 16.0:  # S3 الحل
        lt = t - 10.0
        draw_gem(d, cx, fy(0.15), 66, prog(lt, 0))
        centered(d, cx, fy(0.215), S("حزمة جوهرة"), F(84), with_alpha(GOLD, prog(lt, 0.3)))
        icons = []
        for i in range(5):
            icons.append("check" if lt > 1.2 + i * 0.75 else None)
        draw_sheet(d, 90, fy(0.345), W - 180, icons, rh=int(H * 0.052), a=prog(lt, 0.6))
        centered(d, cx, fy(0.345) + int(H * 0.052) * 6 + 44, S("تفحص بياناتك بـ 24 بنداً في 6 محاور"),
                 F(46), with_alpha(WHITE, prog(lt, 4.6)))

    elif t < 24.0:  # S4 المحاور
        lt = t - 16.0
        centered(d, cx, fy(0.12), S("ستة محاور تغطي كل شيء"), F(62), with_alpha(WHITE, prog(lt, 0)))
        colw = (W - 180 - 30) // 2
        ch_h = int(H * 0.082)
        y0 = fy(0.235)
        for i, name in enumerate(AXES):
            r, c = divmod(i, 2)
            x = 90 + c * (colw + 30)
            y = y0 + r * (ch_h + int(H * 0.018))
            p = prog(lt, 0.5 + i * 0.8)
            yy = y + int((1 - p) * 34)
            d.rounded_rectangle([x, yy, x + colw, yy + ch_h], radius=18,
                                fill=with_alpha(PANEL, p), outline=with_alpha(PANEL_LINE, p), width=2)
            draw_icon(d, x + colw - 46, yy + ch_h // 2, 19, "check", p)
            right_text(d, x + colw - 82, yy + ch_h // 2 - 30, S(name), F(38), with_alpha(WHITE, p))
        ly = y0 + 3 * ch_h + int(H * 0.075)
        legend = [("ناجح", "check", GREEN), ("يحتاج مراجعة", "warn", AMBER), ("فشل", "x", RED)]
        total_w = 0
        widths = []
        for name, _, _ in legend:
            b = d.textbbox((0, 0), S(name), font=F(36))
            widths.append(b[2] - b[0] + 66)
            total_w += widths[-1] + 36
        x = cx - (total_w - 36) // 2
        p = prog(lt, 5.6)
        for (name, ic, _), wd in zip(legend, widths):
            draw_icon(d, x + wd - 24, ly + 24, 19, ic, p)
            right_text(d, x + wd - 56, ly, S(name), F(36), with_alpha(WHITE, p))
            x += wd + 36

    elif t < 30.0:  # S5 المحتويات
        lt = t - 24.0
        centered(d, cx, fy(0.13), S("ماذا تستلم؟"), F(66), with_alpha(WHITE, prog(lt, 0)))
        items = [("ملف Excel تفاعلي", "6 أوراق: بيانات، تحقق، سجل، أخطاء، مؤشرات", "check"),
                 ("دليل استخدام PDF", "خطوات واضحة من الصفر حتى الاعتماد", "check"),
                 ("قائمة تحقق مطبوعة", "24 بنداً جاهزة للعمل الورقي السريع", "check")]
        y = fy(0.26)
        for i, (ti, su, ic) in enumerate(items):
            p = prog(lt, 0.5 + i * 1.3)
            card_row(d, 90, y, W - 180, int(H * 0.105), ic, ti, su, p, dy=int((1 - p) * 46))
            y += int(H * 0.105) + int(H * 0.022)
        centered(d, cx, y + 26, S("استلام فوري على واتساب بعد الشراء"), F(44), with_alpha(TEAL, prog(lt, 4.6)))

    else:  # S6 الختام الذهبي
        lt = t - 30.0
        p = prog(lt, 0, 0.9)
        gold = Image.new("RGBA", (W, H), GOLD_RGB + (int(255 * p),))
        img.alpha_composite(gold)
        d = ImageDraw.Draw(img)
        a = prog(lt, 0.7)
        centered(d, cx, fy(0.20), S("جوهرة"), F(110), with_alpha(NAVY_TEXT, a))
        centered(d, cx, fy(0.20) + 150, S("حزمة تدقيق البيانات الكاملة"), F(50), with_alpha(NAVY_TEXT, a))
        centered(d, cx, fy(0.42), S("20 دولاراً فقط"), F(104), with_alpha(NAVY_TEXT, prog(lt, 1.4)))
        by = fy(0.58)
        bw, bh = W - 220, max(int(H * 0.115), 175)
        pp = prog(lt, 2.2)
        d.rounded_rectangle([cx - bw // 2, by, cx + bw // 2, by + bh], radius=26,
                            fill=with_alpha(NAVY_TEXT, pp))
        centered(d, cx, by + 26, S("اطلبها الآن عبر واتساب"), F(48), with_alpha(WHITE, pp))
        centered(d, cx, by + 92, "00218-918199601", F(52), with_alpha(GOLD, pp))
        centered(d, cx, by + bh + 36, S("دفعة واحدة — بلا اشتراكات"), F(38, bold=False), with_alpha(NAVY_TEXT, prog(lt, 3.0)))

    return img.convert("RGB")


def encode(W, H, out_name):
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    out = BASE / out_name
    cmd = [exe, "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-crf", "23", "-preset", "medium", "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    frames = int(FPS * DUR)
    for i in range(frames):
        frame = render_frame(W, H, i / FPS)
        proc.stdin.write(frame.tobytes())
        if i % 75 == 0:
            print(f"  {out_name}: frame {i}/{frames}", flush=True)
    proc.stdin.close()
    proc.wait()
    print(out.name, out.stat().st_size, "bytes")


if __name__ == "__main__":
    print("Rendering vertical 1080x1920...")
    encode(1080, 1920, "jawhara-ad-video-vertical.mp4")
    print("Rendering square 1080x1080...")
    encode(1080, 1080, "jawhara-ad-video-square.mp4")
    print("VIDEO OK")

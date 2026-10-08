#!/usr/bin/env python3
"""التحقق من صور الموقع قبل الرفع وبعده.

يقرأ index.html، يستخرج كل إشارة لصورة محلية (src="..." أو url("..."))،
ثم يتأكد أن الملف موجود فعلاً، وأن محتواه صورة حقيقية (magic bytes)،
وأن حجمه منطقي، ويطبع أبعاده. أي خلل يخرج بكود 1 مع رسالة واضحة.

الاستخدام:  python3 scripts/check-images.py [path/to/index.html]
"""

from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIN_PHOTO_BYTES = 5_000  # صورة حقيقية لا يمكن أن تكون 76 بايت
MAX_GITHUB_BLOB = 100 * 1024 * 1024  # حد GitHub للملف الواحد

SIGNATURES = {
    b"\xff\xd8\xff": "JPEG",
    b"\x89PNG\r\n\x1a\n": "PNG",
    b"GIF87a": "GIF",
    b"GIF89a": "GIF",
    b"BM": "BMP",
}


def sniff_format(data: bytes) -> str | None:
    for sig, name in SIGNATURES.items():
        if data.startswith(sig):
            return name
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "WEBP"
    head = data[:400].lstrip().lower()
    if head.startswith(b"<svg") or head.startswith(b"<?xml"):
        return "SVG"
    return None


def jpeg_size(data: bytes) -> tuple[int, int] | None:
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        length = struct.unpack(">H", data[i + 2 : i + 4])[0]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            h, w = struct.unpack(">HH", data[i + 5 : i + 9])
            return w, h
        i += 2 + length
    return None


def png_size(data: bytes) -> tuple[int, int] | None:
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) > 24:
        w, h = struct.unpack(">II", data[16:24])
        return w, h
    return None


def dimensions(name: str, data: bytes) -> str:
    if name.endswith(".svg") or sniff_format(data) == "SVG":
        m = re.search(rb'viewBox="([^"]+)"', data)
        if m:
            parts = m.group(1).split()
            if len(parts) == 4:
                return f"{float(parts[2]):.0f}x{float(parts[3]):.0f}"
        return "متجه SVG"
    size = jpeg_size(data) or png_size(data)
    return f"{size[0]}x{size[1]}" if size else "غير معروف"


def local_refs(html: str) -> list[str]:
    refs: list[str] = []
    for m in re.finditer(r'(?:src|href)\s*=\s*"([^"]+)"', html):
        refs.append(m.group(1))
    for m in re.finditer(r'url\(\s*["\']?([^"\')]+)["\']?\s*\)', html):
        refs.append(m.group(1))
    # مسارات الـ fallback المكتوبة جوه onerror="this.src='...'"
    for m in re.finditer(r"src\s*=\s*'([^']+)'", html):
        refs.append(m.group(1))
    out = []
    for r in refs:
        if r.startswith(("http://", "https://", "data:", "#", "mailto:", "tel:", "//")):
            continue
        if r not in out:
            out.append(r)
    return out


def check_file(path: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    notes: list[str] = []
    data = path.read_bytes()
    fmt = sniff_format(data)
    if fmt is None:
        head = data[:60].decode("utf-8", "replace").replace("\n", " ")
        errors.append(
            f"الملف ليس صورة صالحة — أول بايت هي {data[:4]!r}. "
            f"محتواه نص: «{head}». (غالبًا placeholder لم يُستبدل)"
        )
    elif fmt != "SVG":
        if len(data) < MIN_PHOTO_BYTES:
            errors.append(f"حجم الملف {len(data)} بايت فقط — أقل من {MIN_PHOTO_BYTES} بايت، مستحيل تكون صورة حقيقية")
        if len(data) > MAX_GITHUB_BLOB:
            errors.append(f"حجم الملف {len(data)/1e6:.1f}MB يتجاوز حد GitHub (100MB) ولن يُرفع")
        ext = path.suffix.lower()
        expected = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".gif": "GIF", ".webp": "WEBP", ".bmp": "BMP"}
        if expected.get(ext) and expected[ext] != fmt:
            notes.append(
                f"⚠ الامتداد {ext} لكن المحتوى {fmt} — المتصفح هيتحمّله، لكن "
                f"الأفضل تسمية الملف {path.stem}.{fmt.lower()}"
            )
    notes.insert(0, f"النوع: {fmt or '—'}  |  المقاس: {dimensions(path.name, data)}  |  الحجم: {len(data)/1024:.0f}KB")
    return errors, notes


def main() -> int:
    html_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "index.html"
    if not html_path.exists():
        print(f"✗ ملف HTML غير موجود: {html_path}")
        return 1

    html = html_path.read_text(encoding="utf-8")
    base = html_path.parent
    problems = 0

    print("=== فحص الصور المشار إليها في الموقع ===")
    for ref in local_refs(html):
        target = (base / ref).resolve()
        rel = target.relative_to(ROOT) if str(target).startswith(str(ROOT)) else target
        if not target.exists():
            print(f"✗ {ref}\n   الملف غير موجود في المستودع → ارفعه أولاً ({rel})")
            problems += 1
            continue
        errors, notes = check_file(target)
        for e in errors:
            print(f"✗ {ref}\n   {e}")
            problems += 1
        if not errors:
            print(f"✓ {ref}  ({notes[0]})")

    print("\n=== فحص كل الملفات داخل images/ ===")
    img_dir = ROOT / "images"
    referenced = {(base / r).resolve().name for r in local_refs(html)}
    found = False
    for path in sorted(img_dir.glob("*")):
        if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}:
            continue
        found = True
        errors, notes = check_file(path)
        unused = "" if path.name in referenced else "  ⚠ غير مستخدمة في index.html"
        if errors:
            for e in errors:
                print(f"✗ images/{path.name}\n   {e}{unused}")
                problems += 1
        else:
            print(f"✓ images/{path.name}  ({notes[0]}){unused}")
    if not found:
        print("⚠ مجلد images/ لا يحتوي أي صور — ارفع ملفات JPG/PNG بأسماء الملفات المطلوبة في index.html")

    print()
    if problems:
        print(f"مجموع المشاكل: {problems}. أصلحها ثم أعد التشغيل.")
        return 1
    print("كل الصور سليمة ومرتبطة بالموقع ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

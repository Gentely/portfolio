#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
تشغيل أداة سجل السرطان المستقلة
================================
    python3 run.py                        → http://localhost:8765
    python3 run.py --port 9000
    python3 run.py --host 0.0.0.0 --port 8765   → للوصول من أجهزة أخرى في الشبكة
    python3 run.py --storage /mnt/registry      → مجلد تخزين مختلف
    python3 run.py --demo                     → يحمّل السجلات النموذجية أولاً

المتطلبات:  pip install -r requirements.txt
"""

from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def main():
    ap = argparse.ArgumentParser(description="أداة سجل السرطان — Cancer Registry Tool")
    ap.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"),
                    help="العنوان المستمع (default: 127.0.0.1)")
    ap.add_argument("--port", type=int, default=int(os.getenv("PORT", 8765)))
    ap.add_argument("--storage", default=os.getenv("CR_STORAGE_DIR"),
                    help="مجلد التخزين (default: ./storage)")
    ap.add_argument("--demo", action="store_true", help="يحمّل النماذج من samples/ أولاً")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    if args.storage:
        os.environ["CR_STORAGE_DIR"] = str(Path(args.storage).resolve())

    from crcore import ocr, pipeline, storage
    storage.init_storage()

    if args.demo:
        samples = ROOT / "samples"
        if samples.exists():
            print("— جارٍ تحميل النماذج التجريبية…")
            out = pipeline.process_batch([str(samples)])
            print(f"  تمّت معالجة {out['processed']} ملف، فشل {out['failed']}")

    st = ocr.engine_status()
    print()
    print("═" * 66)
    print("  🏥  سجل السرطان — Cancer Registry Tool")
    print("═" * 66)
    print(f"  التخزين      : {storage.BASE_DIR}")
    print(f"  السجلات      : {storage.stats()['total_cases']}")
    print(f"  Tesseract    : {'✓ مثبّت' if st['tesseract'] else '✗ غير مثبّت'}"
          f"{'  (العربية ✓)' if st.get('arabic_supported') else ''}")
    print(f"  نص PDF مدمج  : {'✓' if (st['pypdf'] or st['pdfminer']) else '✗'}")
    print(f"  pdftoppm     : {'✓' if st['pdftoppm'] else '✗ (مطلوب لـ OCR على PDF)'}")
    if st["note"]:
        print()
        print("  ⚠ " + st["note"])
    print("═" * 66)
    url = f"http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}"
    print(f"  ▶ افتح المتصفح على:  {url}")
    print("═" * 66)
    print()

    if not args.no_browser and args.host in ("127.0.0.1", "localhost", "0.0.0.0"):
        try:
            webbrowser.open(url)
        except Exception:
            pass

    from webapp.app import app
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True,
            use_reloader=args.debug)


if __name__ == "__main__":
    main()

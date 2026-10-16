#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
معالجة دفعة كاملة من السطر الأوامر (بدون واجهة رسومية)
=======================================================
الأنسب عندما يكون لديك مجلد كامل من الملفات الممسوحة ضوئياً.

أمثلة:
  # معالجة مجلد كامل وتصدير Excel
  python3 cli.py process ./scans --excel سجلات_2026.xlsx

  # بأفضل محرك OCR وبدون حفظ (للمعاينة فقط)
  python3 cli.py process ./scans --no-save --show

  # من نص ملصوق / ملف نصي واحد
  python3 cli.py process ./report.txt --show

  # فحص الجودة فقط على السجلات المحفوظة
  python3 cli.py qc

  # تصدير كل السجلات المحفوظة إلى Excel
  python3 cli.py export --out /tmp/registry.xlsx

  # حالة النظام والمحركات
  python3 cli.py status
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from crcore import dictionary as dic
from crcore import extractor, ocr, pipeline, quality, reference, storage
from crcore.dictionary import option_label


def _print_record(rec: dict, hits: dict = None, lang: str = "ar"):
    hits = hits or {}
    print("─" * 78)
    for g, names in dic.GROUPS.items():
        rows = [(n, rec.get(n)) for n in names
                if n in rec and rec.get(n) not in (None, "")]
        if not rows:
            continue
        print(f"◆ {g}")
        for n, v in rows:
            f = dic.FIELDS[n]
            disp = option_label(n, str(v), lang) if f["type"] == "selection" else str(v)
            h = hits.get(n)
            tag = f"  [{h['method']} {h['confidence']:.0%}]" if h else ""
            flag = "✓" if f["required"] else " "
            print(f"  {flag} {f['label_ar']:<28s} {disp[:44]:<46s}{tag}")
    print("─" * 78)


def cmd_process(a):
    paths = a.paths
    print(f"→ معالجة {len(paths)} مسار…")
    out = pipeline.process_batch(paths, prefer=a.engine, lang=a.lang, save=not a.no_save)

    print()
    print(f"✓ تمت المعالجة: {out['processed']}   ✗ فشل: {out['failed']}")
    if out["failed"]:
        for f in out["failures"]:
            print(f"   ! {f['file']}: {f['error']}")

    for r in out["results"]:
        rec = r["record"]
        print()
        print(f"━━ {r['file']}  →  {r['registry_no']}")
        print(f"   المحرك: {r['ocr']['engine']}   ثقة الاستخراج: {r['extraction']['confidence']}%"
              f"   الحقول: {len(r['extraction']['values'])}")
        for w in (r["ocr"].get("warnings") or [])[:3]:
            print(f"   ⚠ OCR: {w}")
        if a.show:
            _print_record(rec, r["extraction"]["hits"])
        qc = r["qc"]
        print(f"   الجودة: {qc.get('score')}/100 ({qc.get('status')}) — "
              f"{qc.get('errors')} خطأ، {qc.get('warnings')} تحذير")
        if a.verbose:
            for i in qc.get("issues", []):
                if i["severity"] == "info":
                    continue
                icon = {"error": "✗", "warning": "⚠"}[i["severity"]]
                print(f"      {icon} [{i['code']}] {i['message']}")
                if i.get("fix"):
                    print(f"         → {i['fix']}")
        print(f"   الأرشيف: {r['archive_path']}")

    bqc = out["batch_qc"]
    print()
    print("═" * 78)
    print(f"فحص الدفعة: {bqc['total']} سجل · متوسط النقاط {bqc['avg_score']} · "
          f"{bqc['by_status']}")
    if bqc.get("duplicates"):
        print(f"⚠ تكرار مشتبه: {len(bqc['duplicates'])} مجموعة")
        for d in bqc["duplicates"][:10]:
            print(f"   {d['key']}  →  {d['records']}")
    if bqc.get("top_issues"):
        print("أكثر المشاكل تكراراً:")
        for code, n in bqc["top_issues"][:8]:
            cat = quality.RULE_CATALOGUE.get(code, ("", code))
            print(f"   {code} ×{n}  {cat[1]}")
    print("═" * 78)

    if a.excel:
        p = pipeline.export_all(out_path=a.excel, meta={"facility": a.facility or ""})
        print(f"\n📥 تم التصدير إلى: {p}")


def cmd_qc(a):
    cases = storage.all_cases()
    if not cases:
        print("لا توجد سجلات محفوظة. استخدم: python3 cli.py process <مسار>")
        return 1
    if getattr(a, "registry", None):
        wanted = [w.strip() for w in str(a.registry).split(",") if w.strip()]
        cases = [c for c in cases
                 if c["case"].get("registry_no", "") in wanted]
        if not cases:
            print(f"لا يوجد سجل بالرقم {a.registry}")
            return 1
    records = [c["case"] for c in cases]
    batch = quality.check_batch(records)
    print(f"فحص {batch['total']} سجل — متوسط النقاط {batch['avg_score']}/100")
    print(f"  مطابق: {batch['by_status'].get('pass',0)}   "
          f"تحذير: {batch['by_status'].get('warning',0)}   "
          f"خطأ: {batch['by_status'].get('error',0)}")
    # ترشيح حسب الحالة / الأخطاء فقط
    if getattr(a, "status", None):
        batch["reports"] = [(r, rp) for r, rp in batch["reports"]
                            if rp.status == a.status]
    if getattr(a, "only_errors", False):
        batch["reports"] = [(r, rp) for r, rp in batch["reports"]
                            if rp.status == "error"]
    if not batch["reports"]:
        print("\nلا توجد سجلات مطابقة للمرشّح.")
        return 0
    print()
    for rec, rep in batch["reports"]:
        icon = {"pass": "✓", "warning": "⚠", "error": "✗", "not_run": "?"}[rep.status]
        print(f"{icon} {rec.get('registry_no','?'):<14s} {rep.score:>3}/100  "
              f"{rec.get('full_name','—')[:32]:<34s} "
              f"E{len(rep.errors)} W{len(rep.warnings)}")
        if a.verbose:
            for i in rep.issues:
                if i.severity == "info":
                    continue
                print(f"      [{i.code}] {i.message}")
                if i.fix:
                    print(f"         → {i.fix}")
    if batch.get("duplicates"):
        print(f"\n⚠ {len(batch['duplicates'])} مجموعة تكرار مشتبه:")
        for d in batch["duplicates"][:20]:
            print(f"   {d['key']} → {d['records']}")
    return 1 if any(rep.status == "error" for _, rep in batch["reports"]) else 0


def cmd_export(a):
    try:
        p = pipeline.export_all(out_path=a.out, only_validated=a.only_validated,
                                meta={"facility": a.facility or "", "author": a.author or ""})
    except ValueError as exc:
        print(f"✗ {exc}")
        return 1
    print(f"📥 تم التصدير: {p}")
    return 0


def cmd_status(a):
    st = pipeline.dashboard()
    e = st["engines"]
    print("═" * 66)
    print("  حالة النظام — Cancer Registry Tool")
    print("═" * 66)
    print(f"  الإصدار        : {st['version']}")
    print(f"  التخزين        : {st['storage_dir']}")
    print(f"  السجلات        : {st['total_cases']}")
    print(f"  المستندات      : {st['total_documents']}")
    print(f"  متوسط الجودة   : {st['avg_qc_score']}/100")
    print(f"  جداول ICD-O-3  : {st['refdata']['topography_codes']} موقع · "
          f"{st['refdata']['morphology_codes']} نسيج · {st['refdata']['tnm_rules']} قاعدة TNM")
    print(f"  جداول ICD-10   : {st['refdata']['icd10_codes']}")
    print("─" * 66)
    for k, lbl in [("tesseract", "Tesseract OCR"), ("arabic_supported", "  دعم العربية"),
                   ("pdftoppm", "pdftoppm (poppler)"), ("pypdf", "pypdf"),
                   ("pdfminer", "pdfminer"), ("azure_di", "Azure Document Intelligence"),
                   ("openai", "OpenAI API")]:
        v = e.get(k)
        print(f"  {lbl:<26s} {'✓' if v else '✗'}")
    if e.get("tesseract_languages"):
        print(f"  لغات Tesseract   : {', '.join(e['tesseract_languages'])}")
    if e.get("note"):
        print("\n  ⚠ " + e["note"])
    print("═" * 66)
    if st.get("by_site"):
        print("  أعلى المواقع:")
        for k, n in list(st["by_site"].items())[:10]:
            print(f"    {n:>4}  {k}")
    return 0


def cmd_dictionary(a):
    print(f"قاموس الحقول — {len(dic.FIELDS)} حقل "
          f"({len(dic.REQUIRED_FIELDS)} إلزامي)\n")
    groups = dic.GROUPS
    if getattr(a, "group", None):
        key = str(a.group).strip().upper()
        groups = {g: n for g, n in dic.GROUPS.items()
                  if g.split(".")[0].strip().upper() == key
                  or g.upper().startswith(key + ".")
                  or g.split(".")[0].strip().upper().startswith(key)}
        if not groups:
            print(f"لا توجد مجموعة بالرمز {a.group} — المجموعات: "
                  + "، ".join(g.split(".")[0] for g in dic.GROUPS))
            return 1
    for g, names in groups.items():
        print(f"◆ {g}")
        for n in names:
            f = dic.FIELDS[n]
            if getattr(a, "required", False) and not f["required"]:
                continue
            req = " [إلزامي]" if f["required"] else ""
            opts = ""
            if f["options"]:
                opts = "  ← " + " | ".join(list(f["options"].keys())[:6])
                if len(f["options"]) > 6:
                    opts += f" … (+{len(f['options'])-6})"
            print(f"  {f['name']:<24s} {f['label_ar']:<30s} {f['type']:<10s}{req}{opts}")
        print()
    if a.csv:
        import csv as _csv
        with open(a.csv, "w", encoding="utf-8-sig", newline="") as fh:
            w = _csv.writer(fh)
            w.writerow(["group", "name", "label_ar", "label_en", "type", "required",
                        "options", "reference", "help"])
            for f in dic.DATA_DICTIONARY:
                w.writerow([f["group"], f["name"], f["label_ar"], f["label_en"], f["type"],
                            "yes" if f["required"] else "",
                            " | ".join(f"{k}={v[0]}" for k, v in (f["options"] or {}).items()),
                            f["ref"], f["help_ar"]])
        print(f"📥 تم حفظ القاموس: {a.csv}")
    return 0


def cmd_extract(a):
    """استخراج من ملف واحد وعرض النتيجة بصيغة JSON (للتكامل مع أنظمة أخرى)."""
    r = pipeline.read_and_extract(a.path, prefer=a.engine, lang=a.lang)
    if a.json and not a.show:
        print(json.dumps({"record": r["record"], "extraction": r["extraction"],
                          "ocr": {k: v for k, v in r["ocr"].items() if k != "text"}},
                         ensure_ascii=False, indent=2, default=str))
    else:
        _print_record(r["record"], r["extraction"]["hits"])
        print(f"\nالثقة: {r['extraction']['confidence']}%   المحرك: {r['ocr']['engine']}")
        rep = quality.check_case(r["record"])
        print(rep.to_text())
    return 0


def main():
    ap = argparse.ArgumentParser(prog="cli.py", description="أداة سجل السرطان — سطر الأوامر")
    ap.add_argument("--storage", help="مجلد التخزين")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("process", help="معالجة ملفات/مجلدات")
    p.add_argument("paths", nargs="+")
    p.add_argument("--engine", default="auto",
                   choices=["auto", "tesseract", "embedded", "azure", "manual"])
    p.add_argument("--lang", default="ara+eng")
    p.add_argument("--excel", help="مسار ملف Excel الناتج")
    p.add_argument("--facility", help="اسم الجهة في ترويسة التصدير")
    p.add_argument("--no-save", action="store_true")
    p.add_argument("--show", action="store_true", help="يعرض الحقول المستخرجة")
    p.add_argument("-v", "--verbose", action="store_true", help="يعرض كل مشاكل الجودة")
    p.set_defaults(func=cmd_process)

    p = sub.add_parser("qc", help="فحص جودة السجلات المحفوظة")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="يعرض كل مشكلة لكل سجل")
    p.add_argument("--only-errors", action="store_true",
                   help="السجلات التي بها أخطاء فقط — لقائمة العمل اليومية")
    p.add_argument("--status", choices=["pass", "warning", "error", "not_run"],
                   help="ترشيح حسب حالة الجودة")
    p.add_argument("--registry", help="أرقام سجلات محددة مفصولة بفواصل")
    p.set_defaults(func=cmd_qc)

    p = sub.add_parser("export", help="تصدير Excel")
    p.add_argument("--out")
    p.add_argument("--only-validated", action="store_true")
    p.add_argument("--facility")
    p.add_argument("--author")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("extract", help="استخراج من ملف واحد")
    p.add_argument("path")
    p.add_argument("--engine", default="auto")
    p.add_argument("--lang", default="ara+eng")
    p.add_argument("--json", action="store_true",
                   help="مخرجات JSON للتكامل مع أنظمة أخرى")
    p.add_argument("--show", action="store_true",
                   help="عرض جدول الحقول المستخرجة مع أدلتها (الافتراضي)")
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("status", help="حالة النظام والمحركات")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("dictionary", help="طباعة قاموس الحقول")
    p.add_argument("--csv", help="حفظ القاموس كملف CSV")
    p.add_argument("--group", help="مجموعة واحدة برمزها (A–G)")
    p.add_argument("--required", action="store_true",
                   help="الحقول الإلزامية فقط")
    p.set_defaults(func=cmd_dictionary)

    a = ap.parse_args()
    if a.storage:
        import os
        os.environ["CR_STORAGE_DIR"] = str(Path(a.storage).resolve())
        import importlib
        importlib.reload(storage)
    storage.init_storage()
    sys.exit(a.func(a) or 0)


if __name__ == "__main__":
    main()

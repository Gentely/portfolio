#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
اختبار متكامل لخط المعالجة — بلا خادم
======================================
    python3 tools/test_pipeline.py

يشغّل الملفات التجريبية الخمسة في مخزن مؤقت، ويتحقق من:

  1) الاستخراج: الحقول الإلزامية تُلتقط من كل ملف سليم
  2) الاشتقاق: العمر، سنة التشخيص، السلوك، ICD-10، المرحلة، البقاء
  3) الجودة: الملفات السليمة ≥ 90، والملف المُخرَّب يلتقط كل أخطائه المتعمدة
  4) كشف التكرار: إدخال نفس الملف مرة ثانية يُعلَّم مكرراً
  5) التصدير: ملف Excel صالح بست أوراق وبالترتيب الصحيح
  6) الأرشيف: نفس الملف لا يُخزَّن مرتين، والبصمة محفوظة
  7) وحدة أودو: قاموس الحقول مطابق بين النواتين

لا يمسّ المخزن الحقيقي — يستخدم مجلداً مؤقتاً يُحذف في النهاية.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="cr_test_"))
os.environ["CR_STORAGE_DIR"] = str(TMP)

from crcore import dictionary as dic                      # noqa: E402
from crcore import excel_export, pipeline, quality, reference, storage  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def check(cond, label, detail=""):
    global CHECKS
    CHECKS += 1
    if cond:
        print("   ✓ %s" % label)
    else:
        print("   ✗ %s%s" % (label, (" — " + detail) if detail else ""))
        FAILURES.append(label + ((" — " + detail) if detail else ""))


def main():
    samples = sorted((ROOT / "samples").glob("*.txt")) + \
        sorted((ROOT / "samples").glob("*.pdf"))
    print("الملفات التجريبية: %s" % len(samples))
    storage.init_storage()

    # ══════════════════════════════════════════════════════════════════
    print("\n1) المعالجة والاستخراج")
    results = {}
    for path in samples:
        out = pipeline.process_file(path)
        results[path.name] = out
        rec = out["record"]
        ok = out.get("qc", {}).get("score", 0)
        print("   • %-42s → %-14s جودة %s/100" % (
            path.name, rec.get("registry_no", "?"), ok))
        if path.name != "03_bad_data_qc_demo.txt":
            check(bool(rec.get("national_id")), "%s: الرقم الوطني" % path.name)
            check(bool(rec.get("first_name")) and bool(rec.get("family_name")),
                  "%s: تجزئة الاسم" % path.name)
            check(bool(rec.get("primary_site")) and bool(rec.get("morphology")),
                  "%s: الموقع والفحص النسيجي" % path.name)
            check(bool(rec.get("date_of_diagnosis")),
                  "%s: تاريخ التشخيص" % path.name)

    # ══════════════════════════════════════════════════════════════════
    print("\n2) الحقول المشتقة (ملف الثدي)")
    rec = results["01_breast_fa_119780445231.txt"]["record"]
    check(rec.get("primary_site") == "C50.4", "تطبيع الموقع → C50.4",
          str(rec.get("primary_site")))
    check(rec.get("icd10_code", "").startswith("C50"),
          "اشتقاق ICD-10 من ICD-O-3", str(rec.get("icd10_code")))
    check(rec.get("behaviour") == "3", "اشتقاق السلوك من رمز الفحص النسيجي",
          str(rec.get("behaviour")))
    check(rec.get("age_at_diagnosis") not in (None, "", 0),
          "حساب العمر عند التشخيص", str(rec.get("age_at_diagnosis")))
    check(rec.get("diagnosis_year"), "سنة التشخيص", str(rec.get("diagnosis_year")))
    check(rec.get("summary_stage") in ("localized", "regional", "distant",
                                       "in_situ", "unknown"),
          "اشتقاق المرحلة الموجزة من TNM", str(rec.get("summary_stage")))

    # ══════════════════════════════════════════════════════════════════
    print("\n3) فحص الجودة")
    bad = results["03_bad_data_qc_demo.txt"]
    bad_rep = bad.get("qc") or {}
    codes = {i["code"] for i in bad_rep.get("issues", [])}
    check(bad_rep.get("score", 100) <= 15, "الملف المُخرَّب درجة منخفضة",
          str(bad_rep.get("score")))
    for want in ("Q-B01", "Q-B03", "Q-C02", "Q-C04", "Q-C11"):
        check(want in codes, "التقط القاعدة %s" % want)
    good = results["01_breast_fa_119780445231.txt"].get("qc") or {}
    check(good.get("score", 0) >= 90, "الملف السليم درجة عالية",
          str(good.get("score")))
    errors = [i for i in good.get("issues", []) if i["severity"] == "error"]
    check(not errors, "الملف السليم بلا أخطاء",
          ", ".join(i["code"] for i in errors))

    # ══════════════════════════════════════════════════════════════════
    print("\n4) كشف التكرار")
    dup = pipeline.process_file(ROOT / "samples" / "01_breast_fa_119780445231.txt",
                                registry_no="")
    dup_rec = dup["record"]
    dup_rep = quality.check_case(dup_rec, duplicates=storage.duplicate_keys())
    d_codes = {i.code for i in dup_rep.issues}
    check("Q-D01" in d_codes, "إدخال نفس الحالة مرة ثانية → Q-D01",
          str(d_codes))

    # ══════════════════════════════════════════════════════════════════
    print("\n5) الأرشيف ومنع تكرار الملفات")
    docs = storage.list_documents(results["01_breast_fa_119780445231.txt"]["record"]
                                  ["registry_no"])
    n_before = len(docs)
    info = storage.store_document(
        str(ROOT / "samples" / "01_breast_fa_119780445231.txt"),
        results["01_breast_fa_119780445231.txt"]["record"]["registry_no"],
        original_name="01_breast_fa_119780445231.txt")
    check(bool(info.get("duplicate")), "نفس الملف لا يُخزَّن مرتين")
    docs2 = storage.list_documents(
        results["01_breast_fa_119780445231.txt"]["record"]["registry_no"])
    check(len(docs2) == n_before, "عدد المستندات لم يتغير بعد محاولة التكرار")
    sha = storage.sha256(str(ROOT / "samples" / "01_breast_fa_119780445231.txt"))
    check(len(sha) == 64, "بصمة SHA-256 محسوبة")

    # ══════════════════════════════════════════════════════════════════
    print("\n6) التصدير إلى Excel")
    out_xlsx = TMP / "export_test.xlsx"
    path = pipeline.export_all(out_path=str(out_xlsx),
                               meta={"facility": "اختبار", "author": "آلي"})
    check(os.path.exists(path), "أُنشئ ملف Excel")
    from openpyxl import load_workbook
    wb = load_workbook(path)
    names = wb.sheetnames
    check(len(names) == 6, "ست أوراق", str(names))
    check(names[0] == "السجل", "الورقة الأولى «السجل»", names[0])
    ws = wb["السجل"]
    check(ws.max_row >= 6, "صفوف البيانات موجودة (%s)" % ws.max_row)
    header = [c.value for c in ws[2] if c.value]
    check(len(header) >= 60, "ترويسة ثنائية اللغة (%s عموداً)" % len(header))
    first_data = ws[3][2].value
    check(first_data, "أول سجل في العمود الثالث")
    check("مرجع ICD-O-3" in names, "ورقة مرجع ICD-O-3 موجودة")

    # ══════════════════════════════════════════════════════════════════
    print("\n7) تطابق النواتين (الأداة المستقلة ↔ وحدة أودو)")
    addon_dict = ROOT / "odoo" / "cancer_registry" / "crcore" / "dictionary.py"
    check(addon_dict.exists(), "نسخة النواة مضمّنة داخل وحدة أودو")
    if addon_dict.exists():
        src_main = (ROOT / "crcore" / "dictionary.py").read_text(encoding="utf-8")
        src_addon = addon_dict.read_text(encoding="utf-8")
        check(src_main == src_addon, "القاموس متطابق حرفياً بين النواتين")
    addon_ref = ROOT / "odoo" / "cancer_registry" / "crcore" / "refdata"
    check((addon_ref / "icdo3_morphology.csv").exists(),
          "جداول المرجع مضمّنة في الوحدة")

    # ══════════════════════════════════════════════════════════════════
    print("\n8) لوحات المراجعة")
    dash = pipeline.dashboard()
    check(dash.get("total_cases", 0) >= 5,
          "لوحة المعلومات تعدّ السجلات", str(dash.get("total_cases")))
    check(dash.get("engines", {}).get("pypdf") is True,
          "لوحة المحركات تُبلغ عن pypdf")
    stats = storage.stats()
    check(stats.get("total_cases", 0) >= 6, "إحصاءات المخزن", str(stats.get("total_cases")))
    trail = storage.audit_trail(
        results["01_breast_fa_119780445231.txt"]["record"]["registry_no"])
    check(len(trail or []) >= 1, "سجل التدقيق يُسجَّل أحداث الحالة",
          str(len(trail or [])))

    # ══════════════════════════════════════════════════════════════════
    shutil.rmtree(TMP, ignore_errors=True)
    print("\n" + "═" * 70)
    print("فحوص: %s   نجاح: %s   إخفاق: %s" % (
        CHECKS, CHECKS - len(FAILURES), len(FAILURES)))
    if FAILURES:
        print("\nالإخفاقات:")
        for f in FAILURES:
            print("   ✗ %s" % f)
        sys.exit(1)
    print("✓ كل الفحوص نجحت.")
    print("═" * 70)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
فاحص البيانات المرجعية (ICD-O-3 / TNM / ICD-10)
=================================================
يتحقق من سلامة جداول ``crcore/refdata/*.csv`` التي تعتمد عليها كل
عمليات الترميز والاشتقاق وفحص الجودة:

  icdo3_topography.csv   code | label_en | label_ar | system
  icdo3_morphology.csv   code | label_en | label_ar | behaviour | group
  tnm_stage_groups.csv   site | t | n | m | stage | summary
  icd10_c_sites.csv      code | label_en | label_ar | chapter

القواعد:
  * لا رمز مكرر
  * صيغة الرمز مطابقة للمعيار
  * السلوك (behaviour) = الرقم بعد الشرطة المائلة في رمز الفحص النسيجي
  * لا تسمية فارغة، ولا تسمية عربية بلا حرف عربي
  * كل موقع في جدول المرحلة موجود في جدول المواقع
  * كل رمز ICD-O-3 له نظير ICD-10 (تحذير فقط)

الاستخدام:   python3 tools/check_refdata.py  [--fix]
"""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "crcore" / "refdata"

ERRORS: list[str] = []
WARNINGS: list[str] = []
FIXED: list[str] = []

FIX_MODE = "--fix" in sys.argv

BEHAVIOUR_GROUPS = {
    "0": "Benign", "1": "Uncertain", "2": "In situ",
    "3": "Malignant", "6": "Malignant", "9": "Unspecified",
}

# إصلاحات معروفة وموثَّقة — تُطبَّق بـ --fix
KNOWN_FIXES = {
    "icdo3_morphology.csv": [
        # (رمز خاطئ، تسمية إنجليزية) → (رمز صحيح، سلوك، مجموعة)
        (("8121/1", "Sinonasal papilloma, inverted"),
         ("8122/0", "0", "Benign"),
         "ICD-O-3: الورم الحليمي الجيبي الأنفي المعكوس رمزه 8122/0 وليس 8121/1"),
        (("9590/3", "Malignant lymphoma, non-Hodgkin, NOS"),
         (None, None, None),
         "ICD-O-3: 9590/3 هو «Malignant lymphoma, NOS» فقط — الصف المكرر يُحذف "
         "(غير هودجكن مغطى بـ 9591/3)"),
    ],
}

# أخطاء إملائية معروفة في أسماء المجموعات → الاسم الصحيح
GROUP_TYPO_FIXES = {
    "Lalignant": "Malignant",
    "Mallignant": "Malignant",
    "Bening": "Benign",
    "Uncertian": "Uncertain",
    "Lyphoid": "Lymphoid",
    "Leukemia": "Leukaemia",
}

BEHAVIOUR_FIXES = {
    "8070/6": ("6", "Malignant", "سرطانة حرشفية منتقلة → السلوك /6"),
    "8140/6": ("6", "Malignant", "سرطانة غدية منتقلة → السلوك /6"),
    "8480/6": ("6", "Malignant", "ورم مخاطي كاذب صفاقي → السلوك /6"),
}


def load(name):
    path = REF / name
    if not path.exists():
        ERRORS.append("ملف مفقود: %s" % path.relative_to(ROOT))
        return None, None, []
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        rows = [r for r in reader if r and any(c.strip() for c in r)]
    if not rows:
        ERRORS.append("%s: فارغ" % name)
        return None, None, []
    return name, rows[0], rows[1:]


def save(name, header, body):
    path = REF / name
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(body)


def has_arabic(text):
    return bool(re.search(r"[\u0600-\u06FF]", text or ""))


# ═══════════════════════════════════════════════════════════════════════════
def check_morphology(report_errors=True):
    name, header, body = load("icdo3_morphology.csv")
    if body is None:
        return {}
    expected_header = ["code", "label_en", "label_ar", "behaviour", "group"]
    if header != expected_header:
        ERRORS.append("%s: الترويسة %s — المتوقع %s" % (name, header, expected_header))

    codes = Counter(r[0] for r in body)
    dupes = [c for c, n in codes.items() if n > 1]

    # تطبيق الإصلاحات المعروفة
    if FIX_MODE:
        rules = {k: v for k, v, _note in KNOWN_FIXES.get(name, [])}
        out = []
        for row in body:
            key = (row[0], row[1])
            if key in rules:
                new_code, beh, grp = rules[key]
                if new_code is None:
                    FIXED.append("حُذف الصف المكرر %s (%s)" % (row[0], row[1]))
                    continue
                row = [new_code, row[1], row[2], beh, grp]
                FIXED.append("صُحّح %s → %s (%s)" % (key[0], new_code, row[1]))
            if row[4] in GROUP_TYPO_FIXES:
                FIXED.append("%s: مجموعة «%s» → «%s»"
                             % (row[0], row[4], GROUP_TYPO_FIXES[row[4]]))
                row = [row[0], row[1], row[2], row[3], GROUP_TYPO_FIXES[row[4]]]
            if row[0] in BEHAVIOUR_FIXES and row[3] != BEHAVIOUR_FIXES[row[0]][0]:
                beh, grp, note = BEHAVIOUR_FIXES[row[0]]
                FIXED.append("%s: السلوك %s → %s — %s" % (row[0], row[3], beh, note))
                row = [row[0], row[1], row[2], beh, grp]
            out.append(row)
        if out != body:
            save(name, header, out)
            body = out

    for code, n in codes.items():
        if n > 1 and not FIX_MODE:
            ERRORS.append("%s: الرمز %s مكرر %s مرات" % (name, code, n))

    table = {}
    for row in body:
        if len(row) != 5:
            ERRORS.append("%s: صف بعدد أعمدة %s: %s" % (name, len(row), row))
            continue
        code, en, ar, beh, grp = row
        table[code] = row
        if not re.match(r"^\d{4}/[0-369]$", code):
            ERRORS.append("%s: صيغة رمز غير صالحة «%s» (المتوقع nnnn/b حيث b ∈ 0,1,2,3,6,9)"
                          % (name, code))
            continue
        if beh != code.split("/")[1]:
            ERRORS.append("%s: %s السلوك المُسجَّل %s لا يطابق رمز السلوك %s"
                          % (name, code, beh, code.split("/")[1]))
        if not en.strip():
            ERRORS.append("%s: %s بلا تسمية إنجليزية" % (name, code))
        if not ar.strip():
            ERRORS.append("%s: %s بلا تسمية عربية" % (name, code))
        elif not has_arabic(ar):
            WARNINGS.append("%s: %s التسمية العربية لا تحتوي حرفاً عربياً: «%s»"
                            % (name, code, ar))
        if grp in GROUP_TYPO_FIXES:
            ERRORS.append("%s: %s مجموعة بها خطأ إملائي «%s» (صوابها «%s»)"
                          % (name, code, grp, GROUP_TYPO_FIXES[grp]))
        if grp not in set(BEHAVIOUR_GROUPS.values()) | {"Lymphoid", "Leukaemia",
                                                         "Melanoma", "Soft tissue",
                                                         "Unspecified"}:
            WARNINGS.append("%s: %s مجموعة غير معتادة «%s»" % (name, code, grp))

    # مجموعة يجب أن تتسق مع السلوك إلا في العائلتين اللمفاوية/اللوكيميا
    for code, row in table.items():
        beh, grp = row[3], row[4]
        if grp in ("Lymphoid", "Leukaemia", "Unspecified"):
            continue
        want = BEHAVIOUR_GROUPS.get(beh)
        if want and grp != want:
            WARNINGS.append("%s: %s السلوك %s يتوقع مجموعة «%s» لكن المسجَّل «%s»"
                            % (name, code, beh, want, grp))

    return table


def check_topography(morph=None):
    name, header, body = load("icdo3_topography.csv")
    if body is None:
        return {}
    if header != ["code", "label_en", "label_ar", "system"]:
        ERRORS.append("%s: الترويسة %s" % (name, header))
    codes = Counter(r[0] for r in body)
    for code, n in codes.items():
        if n > 1:
            ERRORS.append("%s: الرمز %s مكرر %s مرات" % (name, code, n))
    table = {}
    for row in body:
        if len(row) != 4:
            ERRORS.append("%s: صف بعدد أعمدة %s: %s" % (name, len(row), row))
            continue
        code, en, ar, system = row
        table[code] = row
        if not re.match(r"^C\d{2}(\.\d{1,2})?$", code):
            ERRORS.append("%s: صيغة رمز غير صالحة «%s» (المتوقع Cnn.n)" % (name, code))
        num = int(code[1:].split(".")[0])
        # ICD-O-3: C00.0–C80.9 للأورام الصلبة، و C42/C81–C88 للأورام
        # اللمفاوية والدموية (تُستخدم عملياً في السجلات السكانية)
        if not (0 <= num <= 88):
            ERRORS.append("%s: %s خارج نطاق ICD-O-3 (C00–C88)" % (name, code))
        if not en.strip():
            ERRORS.append("%s: %s بلا تسمية إنجليزية" % (name, code))
        if not has_arabic(ar):
            WARNINGS.append("%s: %s تسمية عربية ناقصة: «%s»" % (name, code, ar))
        if not system.strip():
            WARNINGS.append("%s: %s بلا تصنيف جهاز" % (name, code))
    return table


def check_tnm(topo=None):
    name, header, body = load("tnm_stage_groups.csv")
    if body is None:
        return
    if len(header) < 5:
        ERRORS.append("%s: الترويسة %s" % (name, header))
        return
    seen = set()
    for row in body:
        if len(row) != len(header):
            ERRORS.append("%s: صف بعدد أعمدة %s ≠ %s" % (name, len(row), len(header)))
            continue
        key = tuple(row[:len(header) - 1])
        if key in seen:
            WARNINGS.append("%s: قاعدة مكررة %s" % (name, key))
        seen.add(key)
        site = row[0]
        # «ANY» قاعدة عامة تنطبق على كل المواقع — ليست خطأً
        if topo and site and site not in topo \
                and site.upper() not in ("ANY", "ALL", "*") and not site.endswith("*"):
            prefix = site.split(".")[0]
            if prefix not in {t.split(".")[0] for t in topo}:
                WARNINGS.append("%s: قاعدة لموقع غير موجود في جدول المواقع «%s»"
                                % (name, site))
        stage = row[-2] if len(row) > 2 else ""
        if stage and not re.match(
                r"^(Stage\s*)?(0|I{1,3}[ABC]?[123]?|IV[ABC]?[123]?|IS|Unknown|NA|"
                r"Occult|Not\s+applicable|Locali[sz]ed|Regional|Distant|[0-9]+)$",
                stage.strip(), re.IGNORECASE):
            WARNINGS.append("%s: مرحلة بصيغة غريبة «%s»" % (name, stage))


def check_icd10(topo=None):
    name, header, body = load("icd10_c_sites.csv")
    if body is None:
        return {}
    codes = Counter(r[0] for r in body)
    for code, n in codes.items():
        if n > 1:
            ERRORS.append("%s: الرمز %s مكرر %s مرات" % (name, code, n))
    table = {}
    for row in body:
        if len(row) < 3:
            ERRORS.append("%s: صف ناقص: %s" % (name, row))
            continue
        code = row[0]
        table[code] = row
        if not re.match(r"^[CD]\d{2}(\.\d{1,2})?$", code):
            ERRORS.append("%s: صيغة رمز غير صالحة «%s»" % (name, code))
        if not has_arabic(row[2] if len(row) > 2 else ""):
            WARNINGS.append("%s: %s تسمية عربية ناقصة" % (name, code))
    return table


def check_coverage(topo, icd10):
    """كل موقع ICD-O-3 رئيسي يجب أن يكون له نظير ICD-10 (تحذير فقط)."""
    if not topo or not icd10:
        return
    icd10_majors = {c.split(".")[0] for c in icd10}
    majors = sorted({c.split(".")[0] for c in topo})
    missing = [m for m in majors if m not in icd10_majors]
    if missing:
        WARNINGS.append("%s موقعاً رئيسياً بلا نظير ICD-10 (أول 10): %s"
                        % (len(missing), ", ".join(missing[:10])))


# ═══════════════════════════════════════════════════════════════════════════
def main():
    print("فحص البيانات المرجعية في %s…" % REF.relative_to(ROOT))
    morph = check_morphology()
    if FIX_MODE and FIXED:
        # طُبِّقت إصلاحات → أعد الفحص من ملف مُصحَّح للتأكد من زوال الأخطاء
        print("  …أُعيد الفحص بعد الإصلاح")
        morph = check_morphology()
    topo = check_topography(morph)
    check_tnm(topo)
    icd10 = check_icd10(topo)
    check_coverage(topo, icd10)

    print("  المواقع (Topography): %s رمز" % len(topo))
    print("  الفحص النسيجي (Morphology): %s رمز" % len(morph))
    print("  قواعد TNM: %s" % (sum(1 for _ in (REF / 'tnm_stage_groups.csv').open(encoding='utf-8')) - 1))
    print("  رموز ICD-10: %s" % len(icd10))

    if FIXED:
        print("\n✓ %s إصلاح طُبِّق:" % len(FIXED))
        for f in FIXED:
            print("   • %s" % f)

    print("\n" + "═" * 70)
    if WARNINGS:
        print("⚠ %s تحذير:" % len(WARNINGS))
        for w in WARNINGS[:40]:
            print("   • %s" % w)
        if len(WARNINGS) > 40:
            print("   … و%s تحذيراً آخر" % (len(WARNINGS) - 40))
    if ERRORS:
        print("✗ %s خطأ:" % len(ERRORS))
        for e in ERRORS[:60]:
            print("   • %s" % e)
        if len(ERRORS) > 60:
            print("   … و%s خطأً آخر" % (len(ERRORS) - 60))
        if not FIX_MODE:
            print("\nأعد التشغيل بـ --fix لتطبيق الإصلاحات الموثَّقة.")
        sys.exit(1)
    print("✓ البيانات المرجعية سليمة — لا أخطاء.")
    print("═" * 70)


if __name__ == "__main__":
    main()

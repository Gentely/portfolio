# -*- coding: utf-8 -*-
"""
تصدير سجل السرطان إلى Excel
============================
يُنتج مصنفاً (workbook) من عدة أوراق:

  1) السجل            — سجل واحد في كل صف، عناوين ثنائية اللغة، قوائم منسدلة
  2) العلاج           — سطر لكل علاج (تفصيل الـ one2many)
  3) جودة البيانات    — كل مشكلة في سطر مع رمز القاعدة والإصلاح المقترح
  4) ملخص الفحص       — إحصاءات الدفعة وأعلى المشاكل تكراراً والتكرارات
  5) قاموس الحقول     — القاموس كاملاً (يُسلَّم لأي جهة طلبت تعريف الحقول)
  6) مرجع ICD-O-3     — جدول المواقع والنسيج للبحث داخل Excel نفسه

كل الأوراق RTL مع تجميد الصف الأول وتصفية تلقائية.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import CellIsRule, FormulaRule

from .dictionary import (DATA_DICTIONARY, EXCEL_COLUMNS, FIELDS, GROUPS,
                         option_label, QC_STATUS)
from . import reference as ref
from . import quality as qc
from .extractor import parse_date, iso

# --------------------------------------------------------------------------
# الألوان
# --------------------------------------------------------------------------
NAVY = "0B2E4D"
BLUE = "184D8E"
LIGHT = "EAF2FB"
ACCENT = "61B7FF"
GREEN = "C6EFCE"
YELLOW = "FFEB9C"
RED = "FFC7CE"
GREY = "F2F2F2"

THIN = Side(style="thin", color="C9D6E4")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

HDR_FONT = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
SUB_FONT = Font(name="Calibri", size=9, color="1F3B57")
CELL_FONT = Font(name="Calibri", size=10)
TITLE_FONT = Font(name="Calibri", size=14, bold=True, color=NAVY)

HDR_FILL = PatternFill("solid", fgColor=NAVY)
SUB_FILL = PatternFill("solid", fgColor=LIGHT)
ALT_FILL = PatternFill("solid", fgColor="F8FBFF")

WRAP = Alignment(horizontal="right", vertical="top", wrap_text=True)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _fmt_value(name: str, value):
    """يحوّل القيمة إلى ما يظهر في Excel (ترجمة القوائم، تنسيق التواريخ)."""
    f = FIELDS.get(name, {})
    if value is None or value == "":
        return ""
    if f.get("type") == "selection":
        return option_label(name, str(value), "ar")
    if f.get("type") == "boolean":
        return "نعم" if str(value).lower() in ("true", "1", "yes", "نعم") else "لا"
    if f.get("type") in ("date", "datetime"):
        d = parse_date(value) if f.get("type") == "date" else None
        return iso(d) if d else str(value)
    return value


# ==========================================================================
#  الورقة الرئيسية: السجل
# ==========================================================================
def _write_registry_sheet(ws, records, lang="ar"):
    cols = EXCEL_COLUMNS
    ws.sheet_view.rightToLeft = True

    # صف العناوين العربية + صف الرموز التقنية
    for i, name in enumerate(cols, start=1):
        f = FIELDS[name]
        c1 = ws.cell(row=1, column=i, value=f["label_ar"])
        c1.font, c1.fill, c1.alignment, c1.border = HDR_FONT, HDR_FILL, CENTER, BORDER
        c2 = ws.cell(row=2, column=i, value=name)
        c2.font, c2.fill, c2.alignment, c2.border = SUB_FONT, SUB_FILL, CENTER, BORDER
        ws.column_dimensions[get_column_letter(i)].width = f.get("export_width", 18)

    for r, rec in enumerate(records, start=3):
        for i, name in enumerate(cols, start=1):
            cell = ws.cell(row=r, column=i, value=_fmt_value(name, rec.get(name)))
            cell.font, cell.alignment, cell.border = CELL_FONT, WRAP, BORDER
            if r % 2 == 0:
                cell.fill = ALT_FILL

    ws.freeze_panes = "C3"
    ws.auto_filter.ref = f"A2:{get_column_letter(len(cols))}{max(2, len(records) + 2)}"
    ws.row_dimensions[1].height = 34
    ws.row_dimensions[2].height = 16

    _add_validations(ws, cols, len(records))
    _add_conditional_formatting(ws, cols, len(records))
    return len(cols)


def _add_validations(ws, cols, nrows):
    """قوائم منسدلة داخل Excel نفسه ليدخل المستخدم يدوياً بدون أخطاء."""
    if nrows <= 0:
        return
    for i, name in enumerate(cols, start=1):
        f = FIELDS[name]
        col = get_column_letter(i)
        rng = f"{col}3:{col}{nrows + 2}"

        if f["type"] == "selection" and f["options"]:
            labels = [v[0] for v in f["options"].values()]
            # حدّ Excel: 255 حرفاً في قائمة inline → القوائم الطويلة تذهب إلى ورقة مخفية
            joined = ",".join(labels)
            if len(joined) > 240:
                continue
            dv = DataValidation(type="list", formula1=f'"{joined}"', allow_blank=True,
                                showErrorMessage=True, errorTitle="قيمة غير معتمدة",
                                error="اختر قيمة من القائمة المعتمدة في قاموس الحقول.")
            ws.add_data_validation(dv)
            dv.add(rng)

        elif f["type"] == "date":
            dv = DataValidation(type="date", operator="between",
                                formula1="DATE(1900,1,1)", formula2="DATE(2100,12,31)",
                                allow_blank=True, showErrorMessage=True,
                                errorTitle="تاريخ غير صالح",
                                error="أدخل تاريخاً بالصيغة YYYY-MM-DD")
            ws.add_data_validation(dv)
            dv.add(rng)

        elif f["type"] == "integer":
            dv = DataValidation(type="whole", operator="between", formula1="0",
                                formula2="4000", allow_blank=True, showErrorMessage=True,
                                errorTitle="رقم غير صالح", error="أدخل رقماً صحيحاً موجباً")
            ws.add_data_validation(dv)
            dv.add(rng)

        elif name == "national_id":
            dv = DataValidation(type="textLength", operator="equal", formula1="12",
                                allow_blank=True, showErrorMessage=True,
                                errorTitle="الرقم الوطني",
                                error="الرقم الوطني الليبي يجب أن يكون 12 رقماً بالضبط")
            ws.add_data_validation(dv)
            dv.add(rng)

        elif name == "primary_site":
            dv = DataValidation(type="custom", formula1=f'=OR({col}3="",AND(LEFT({col}3,1)="C",'
                                                        f'ISNUMBER(VALUE(MID({col}3,2,2)))))',
                                allow_blank=True, showErrorMessage=True,
                                errorTitle="ICD-O-3", error="الصيغة: C00.0 إلى C80.9")
            ws.add_data_validation(dv)
            dv.add(rng)


def _add_conditional_formatting(ws, cols, nrows):
    """تلوين تلقائي لحالة الجودة والحالة الحيوية."""
    if nrows <= 0:
        return
    for name in ("qc_status", "data_entry_status", "vitality_status"):
        if name not in cols:
            continue
        i = cols.index(name) + 1
        col = get_column_letter(i)
        rng = f"{col}3:{col}{nrows + 2}"
        ws.conditional_formatting.add(rng, FormulaRule(
            formula=[f'OR(ISNUMBER(SEARCH("خطأ",{col}3)),ISNUMBER(SEARCH("فشل",{col}3)),'
                     f'ISNUMBER(SEARCH("متوفى",{col}3)))'],
            fill=PatternFill("solid", fgColor=RED)))
        ws.conditional_formatting.add(rng, FormulaRule(
            formula=[f'OR(ISNUMBER(SEARCH("تحذير",{col}3)),ISNUMBER(SEARCH("مراجعة",{col}3)))'],
            fill=PatternFill("solid", fgColor=YELLOW)))
        ws.conditional_formatting.add(rng, FormulaRule(
            formula=[f'OR(ISNUMBER(SEARCH("ناجح",{col}3)),ISNUMBER(SEARCH("معتمد",{col}3)))'],
            fill=PatternFill("solid", fgColor=GREEN)))

    if "qc_score" in cols:
        i = cols.index("qc_score") + 1
        col = get_column_letter(i)
        rng = f"{col}3:{col}{nrows + 2}"
        ws.conditional_formatting.add(rng, CellIsRule(operator="lessThan", formula=["60"],
                                                      fill=PatternFill("solid", fgColor=RED)))
        ws.conditional_formatting.add(rng, CellIsRule(operator="between", formula=["60", "84"],
                                                      fill=PatternFill("solid", fgColor=YELLOW)))
        ws.conditional_formatting.add(rng, CellIsRule(operator="greaterThanOrEqual",
                                                      formula=["85"],
                                                      fill=PatternFill("solid", fgColor=GREEN)))


# ==========================================================================
#  بقية الأوراق
# ==========================================================================
def _write_treatments_sheet(ws, records):
    headers = [("registry_no", "رقم السجل"), ("patient", "المريض"),
               ("modality", "نوع العلاج"), ("start", "تاريخ البدء"), ("end", "تاريخ الانتهاء"),
               ("facility", "الجهة المنفذة"), ("details", "التفاصيل / البروتوكول"),
               ("cycles", "عدد الدورات"), ("dose", "الجرعة"), ("response", "الاستجابة"),
               ("first_course", "ضمن الدورة الأولى (≤4 أشهر)")]
    ws.sheet_view.rightToLeft = True
    for i, (_k, lbl) in enumerate(headers, start=1):
        c = ws.cell(row=1, column=i, value=lbl)
        c.font, c.fill, c.alignment, c.border = HDR_FONT, HDR_FILL, CENTER, BORDER
        ws.column_dimensions[get_column_letter(i)].width = 22

    from .dictionary import TREATMENT_MODALITY, TREATMENT_RESPONSE
    row = 2
    for rec in records:
        lines = rec.get("_treatments") or []
        if not lines:
            # إن لم توجد أسطر تفصيلية، نبني واحداً من الأعلام
            flags = [(k, v) for k, v in [
                ("surgery", rec.get("surgery_performed")),
                ("chemotherapy", rec.get("chemotherapy_given")),
                ("radiotherapy", rec.get("radiotherapy_given")),
                ("hormonal", rec.get("hormonal_given")),
                ("immunotherapy", rec.get("immunotherapy_given"))]
                if str(v).lower() in ("true", "1", "yes")]
            lines = [{"modality": f, "details": rec.get("treatment_summary", "")} for f, _ in flags]
        for ln in lines:
            vals = [rec.get("registry_no", ""), rec.get("full_name", ""),
                    TREATMENT_MODALITY.get(str(ln.get("modality", "")),
                                           ("", ""))[0] or ln.get("modality", ""),
                    iso(parse_date(ln.get("start_date"))) or ln.get("start_date", ""),
                    iso(parse_date(ln.get("end_date"))) or ln.get("end_date", ""),
                    ln.get("facility", ""), ln.get("details", ""), ln.get("cycles", ""),
                    ln.get("dose", ""),
                    TREATMENT_RESPONSE.get(str(ln.get("response", "")), ("", ""))[0]
                    or ln.get("response", ""),
                    "نعم" if str(ln.get("first_course", "")).lower() in ("true", "1", "yes") else "لا"]
            for i, v in enumerate(vals, start=1):
                c = ws.cell(row=row, column=i, value=v)
                c.font, c.alignment, c.border = CELL_FONT, WRAP, BORDER
                if row % 2 == 0:
                    c.fill = ALT_FILL
            row += 1
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:K{max(1, row - 1)}"
    ws.row_dimensions[1].height = 32


def _write_qc_sheet(ws, batch_result):
    ws.sheet_view.rightToLeft = True
    headers = ["رقم السجل", "المريض", "الخطورة", "رمز القاعدة", "الحقل",
               "اسم الحقل", "المشكلة", "الإصلاح المقترح", "النقاط"]
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=i, value=h)
        c.font, c.fill, c.alignment, c.border = HDR_FONT, HDR_FILL, CENTER, BORDER
    widths = [16, 30, 12, 12, 20, 26, 60, 50, 10]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    row = 2
    for rec, rep in batch_result["reports"]:
        for iss in rep.issues:
            if iss.severity == "info":
                continue
            vals = [rec.get("registry_no", ""), rec.get("full_name", ""),
                    {"error": "خطأ", "warning": "تحذير", "info": "ملاحظة"}[iss.severity],
                    iss.code, iss.field,
                    (FIELDS.get(iss.field) or {}).get("label_ar", iss.field),
                    iss.message, iss.fix, rep.score]
            for i, v in enumerate(vals, start=1):
                c = ws.cell(row=row, column=i, value=v)
                c.font, c.alignment, c.border = CELL_FONT, WRAP, BORDER
            fill = RED if iss.severity == "error" else YELLOW
            for i in range(1, len(vals) + 1):
                ws.cell(row=row, column=i).fill = PatternFill("solid", fgColor=fill)
            row += 1
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:I{max(1, row - 1)}"
    ws.row_dimensions[1].height = 30
    return row - 2


def _write_summary_sheet(ws, batch_result, meta):
    ws.sheet_view.rightToLeft = True
    ws.column_dimensions["A"].width = 44
    ws.column_dimensions["B"].width = 26
    ws.column_dimensions["C"].width = 60

    r = 1
    ws.cell(row=r, column=1, value="ملخص فحص الجودة — سجل السرطان").font = TITLE_FONT
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
    r += 2

    bs = batch_result["by_status"]
    stats = [
        ("تاريخ التصدير", iso(date.today()), ""),
        ("الجهة", meta.get("facility", "مكتب سجل السرطان"), ""),
        ("عدد السجلات في الدفعة", batch_result["total"], ""),
        ("متوسط نقاط الجودة", batch_result["avg_score"], "0-100"),
        ("سجلات مطابقة (Pass)", bs.get("pass", 0), f"{bs.get('pass', 0)}/{max(1, batch_result['total'])}"),
        ("سجلات بتحذير (Warning)", bs.get("warning", 0), ""),
        ("سجلات بها أخطاء (Error)", bs.get("error", 0), "يجب معالجتها قبل التصدير الوطني"),
        ("سجلات مكررة مشتبهة", len(batch_result["duplicates"]), ""),
        ("إجمالي المشاكل المكتشفة", len(batch_result["issues"]), ""),
    ]
    for label, val, note in stats:
        a = ws.cell(row=r, column=1, value=label)
        b = ws.cell(row=r, column=2, value=val)
        c = ws.cell(row=r, column=3, value=note)
        a.font = Font(bold=True, size=10, color=NAVY)
        a.fill, a.border = SUB_FILL, BORDER
        b.font, b.border, b.alignment = CELL_FONT, BORDER, CENTER
        c.font, c.border = SUB_FONT, BORDER
        r += 1

    r += 1
    ws.cell(row=r, column=1, value="أكثر المشاكل تكراراً").font = Font(bold=True, size=12, color=NAVY)
    r += 1
    for i, h in enumerate(["رمز القاعدة", "عدد الحدوث", "وصف القاعدة / المرجع"], start=1):
        c = ws.cell(row=r, column=i, value=h)
        c.font, c.fill, c.alignment, c.border = HDR_FONT, HDR_FILL, CENTER, BORDER
    r += 1
    for code, count in batch_result["top_issues"]:
        cat = qc.RULE_CATALOGUE.get(code, ("", code, "", ""))
        ws.cell(row=r, column=1, value=code).border = BORDER
        ws.cell(row=r, column=2, value=count).border = BORDER
        cc = ws.cell(row=r, column=3, value=f"{cat[1]} — {cat[3]}" if cat[3] else cat[1])
        cc.border, cc.alignment = BORDER, WRAP
        for i in range(1, 4):
            ws.cell(row=r, column=i).font = CELL_FONT
        r += 1

    if batch_result["duplicates"]:
        r += 1
        ws.cell(row=r, column=1, value="السجلات المكررة المشتبهة").font = Font(
            bold=True, size=12, color=NAVY)
        r += 1
        for dup in batch_result["duplicates"][:50]:
            ws.cell(row=r, column=1, value=dup["key"]).border = BORDER
            ws.cell(row=r, column=2,
                    value=", ".join(str(x) for x in dup["records"])).border = BORDER
            for i in (1, 2):
                ws.cell(row=r, column=i).font = CELL_FONT
            r += 1
    ws.freeze_panes = "A3"


def _write_dictionary_sheet(ws):
    ws.sheet_view.rightToLeft = True
    headers = ["المجموعة", "اسم الحقل (تقني)", "التسمية العربية", "Label (EN)",
               "النوع", "إلزامي", "الخيارات المعتمدة", "المرجع المعياري", "ملاحظة"]
    widths = [24, 26, 30, 34, 12, 10, 50, 26, 50]
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=i, value=h)
        c.font, c.fill, c.alignment, c.border = HDR_FONT, HDR_FILL, CENTER, BORDER
        ws.column_dimensions[get_column_letter(i)].width = widths[i - 1]

    r = 2
    for f in DATA_DICTIONARY:
        opts = ""
        if f["options"]:
            opts = " | ".join(f"{k}={v[0]}" for k, v in list(f["options"].items())[:14])
            if len(f["options"]) > 14:
                opts += f" … (+{len(f['options']) - 14})"
        vals = [f["group"], f["name"], f["label_ar"], f["label_en"], f["type"],
                "نعم" if f["required"] else "", opts, f["ref"], f["help_ar"]]
        for i, v in enumerate(vals, start=1):
            c = ws.cell(row=r, column=i, value=v)
            c.font, c.alignment, c.border = CELL_FONT, WRAP, BORDER
            if r % 2 == 0:
                c.fill = ALT_FILL
        r += 1
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:I{r - 1}"
    ws.row_dimensions[1].height = 30


def _write_icdo3_sheet(ws):
    ws.sheet_view.rightToLeft = True
    headers = ["رمز ICD-O-3 (الموقع)", "الاسم بالإنجليزية", "الاسم بالعربية", "الجهاز"]
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=i, value=h)
        c.font, c.fill, c.alignment, c.border = HDR_FONT, HDR_FILL, CENTER, BORDER
    for i, w in enumerate([20, 52, 46, 24], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    r = 2
    for code, row in sorted(ref.topography().items()):
        vals = [code, row.get("label_en", ""), row.get("label_ar", ""), row.get("system", "")]
        for i, v in enumerate(vals, start=1):
            c = ws.cell(row=r, column=i, value=v)
            c.font, c.alignment, c.border = CELL_FONT, WRAP, BORDER
        r += 1

    # قسم النسيج بعد جدولين فارغين
    r += 2
    ws.cell(row=r, column=1, value="ICD-O-3 Morphology — الفحص النسيجي").font = TITLE_FONT
    r += 1
    for i, h in enumerate(["الرمز", "الاسم بالإنجليزية", "الاسم بالعربية", "السلوك", "المجموعة"], start=1):
        c = ws.cell(row=r, column=i, value=h)
        c.font, c.fill, c.alignment, c.border = HDR_FONT, HDR_FILL, CENTER, BORDER
    r += 1
    for code, row in sorted(ref.morphology().items()):
        vals = [code, row.get("label_en", ""), row.get("label_ar", ""),
                row.get("behaviour", ""), row.get("group", "")]
        for i, v in enumerate(vals, start=1):
            c = ws.cell(row=r, column=i, value=v)
            c.font, c.alignment, c.border = CELL_FONT, WRAP, BORDER
        r += 1
    ws.freeze_panes = "A2"


# ==========================================================================
#  نقطة الدخول
# ==========================================================================
def export_records(records: list, out_path, meta: dict = None,
                   include_qc: bool = True, include_dictionary: bool = True,
                   include_refdata: bool = True) -> str:
    """
    يصدر قائمة سجلات إلى ملف Excel.

    records: list[dict] — مفاتيحها أسماء الحقول في القاموس.
             أضف "_treatments": [ {...}, ... ] لسطور العلاج التفصيلية.
    meta:    dict بمعلومات الترويسة (facility, author, period…)
    """
    meta = meta or {}
    wb = Workbook()
    ws = wb.active
    ws.title = "السجل"
    _write_registry_sheet(ws, records)

    wt = wb.create_sheet("العلاج")
    _write_treatments_sheet(wt, records)

    if include_qc:
        batch = qc.check_batch(records)
        wq = wb.create_sheet("جودة البيانات")
        n_issues = _write_qc_sheet(wq, batch)
        wsum = wb.create_sheet("ملخص الفحص")
        _write_summary_sheet(wsum, batch, meta)
    if include_dictionary:
        _write_dictionary_sheet(wb.create_sheet("قاموس الحقول"))
    if include_refdata:
        _write_icdo3_sheet(wb.create_sheet("مرجع ICD-O-3"))

    # خصائص الملف
    wb.properties.title = "سجل السرطان — Cancer Registry Export"
    wb.properties.creator = meta.get("author", "Cancer Registry Office")
    wb.properties.subject = meta.get("facility", "")
    wb.properties.description = (
        f"تصدير {len(records)} سجل — {iso(date.today())} — "
        f"معايير ICD-O-3 / ICD-10 / AJCC 8th / ENCR")

    out_path = str(out_path)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    wb.save(out_path)
    return out_path


def export_single(record: dict, out_path, treatments: list = None) -> str:
    """يصدر سجلاً واحداً (مفيد لزر «تصدير» داخل نموذج الحالة)."""
    rec = dict(record)
    if treatments:
        rec["_treatments"] = treatments
    return export_records([rec], out_path)


def default_filename(prefix: str = "CancerRegistry") -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    return f"{prefix}_{stamp}.xlsx"

# -*- coding: utf-8 -*-
"""
استخراج الحقول من نص التقرير الطبي
====================================
يعمل على نص عربي/إنجليزي مختلط (وهو واقع التقارير الليبية).

المنهجية ثلاث طبقات، وكل طبقة تضيف ثقة:
  1) مطابقة التسميات (Label anchors)  — «الاسم: …», «Name: …», «رقم الوطني …»
  2) مطابقة الأنماط (Pattern mining)   — رموز ICD-O-3، TNM، التواريخ، الرقم الوطني
  3) استنتاج سياقي (Context inference) — اشتقاق ICD-10 والسلوك والمرحلة الموجزة

كل حقل مستخرج يحمل:
  value        القيمة
  confidence   0..1
  method       label | pattern | derived | none
  evidence     المقطع الأصلي من المستند (يُستخدم للتمييز في المعاينة جنباً إلى جنب)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from datetime import date, datetime
from typing import Optional

from . import reference as ref
from .ocr import normalise_text

# ==========================================================================
#  تحليل التواريخ
# ==========================================================================

MONTHS_EN = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

# المصرية/المشرقية + المغاربية/الليبية
MONTHS_AR = {
    "يناير": 1, "كانون الثاني": 1, "جانفي": 1,
    "فبراير": 2, "شباط": 2, "فيفري": 2,
    "مارس": 3, "آذار": 3,
    "ابريل": 4, "أبريل": 4, "نيسان": 4, "افريل": 4, "أفريل": 4,
    "مايو": 5, "ايار": 5, "ماي": 5,
    "يونيو": 6, "حزيران": 6, "جوان": 6,
    "يوليو": 7, "تموز": 7, "جويليه": 7, "جويلية": 7,
    "اغسطس": 8, "أغسطس": 8, "اب": 8, "آب": 8, "اوت": 8, "أوت": 8,
    "سبتمبر": 9, "ايلول": 9, "شتنبر": 9,
    "اكتوبر": 10, "أكتوبر": 10, "تشرين الاول": 10,
    "نوفمبر": 11, "تشرين الثاني": 11,
    "ديسمبر": 12, "كانون الاول": 12, "دجنبر": 12,
}

_DATE_PATTERNS = [
    # 2024-05-13 / 2024/05/13 / 2024.05.13
    (re.compile(r"\b(20\d{2}|19\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b"), "ymd"),
    # 13-05-2024 / 13/05/2024 / 13.05.2024
    (re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2}|19\d{2})\b"), "dmy"),
    # 13 May 2024 / 13 مايو 2024
    (re.compile(r"\b(\d{1,2})\s+([A-Za-z\u0600-\u06FF]+)\s+(20\d{2}|19\d{2})\b"), "dMoY"),
    # May 13, 2024
    (re.compile(r"\b([A-Za-z\u0600-\u06FF]+)\s+(\d{1,2})\s*,?\s+(20\d{2}|19\d{2})\b"), "MoDy"),
    # 2024 فقط
    (re.compile(r"\b(20\d{2}|19\d{2})\b"), "Y"),
]


def parse_date(value) -> Optional[date]:
    """يحوّل أي صيغة تاريخ شائعة إلى date. يُعيد None عند الفشل."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    s = normalise_text(str(value)).strip()
    if not s:
        return None

    for rx, kind in _DATE_PATTERNS:
        m = rx.search(s)
        if not m:
            continue
        try:
            if kind == "ymd":
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            elif kind == "dmy":
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            elif kind == "dMoY":
                d, y = int(m.group(1)), int(m.group(3))
                mo = _month_no(m.group(2))
                if not mo:
                    continue
            elif kind == "MoDy":
                y, d = int(m.group(3)), int(m.group(2))
                mo = _month_no(m.group(1))
                if not mo:
                    continue
            else:  # Y
                return date(int(m.group(1)), 1, 1)
            if mo > 12:                        # تبديل يوم/شهر شائع
                d, mo = mo, d
            return date(y, mo, min(d, 28) if d > 28 and mo == 2 else d)
        except (ValueError, TypeError):
            continue
    return None


def _month_no(token: str) -> int:
    t = token.strip().lower().rstrip(".,")
    if t in MONTHS_EN:
        return MONTHS_EN[t]
    t_ar = token.strip().rstrip(".,")
    t_ar = t_ar.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    if t_ar in MONTHS_AR:
        return MONTHS_AR[t_ar]
    for k, v in MONTHS_AR.items():
        if k.replace("أ", "ا") == t_ar:
            return v
    return 0


def iso(d: Optional[date]) -> str:
    return d.isoformat() if d else ""


# ==========================================================================
#  تسميات الحقول (Label anchors) — عربي + إنجليزي
# ==========================================================================
# كل عنصر: (field, [aliases...], flags)
LABEL_ALIASES = {
    "national_id": [
        r"الرقم\s*الوطني", r"رقم\s*وطني", r"الرقم\s*القومي", r"national\s*(?:id|no\.?|number)",
        r"n\.?i\.?d", r"ليبيا\s*\d",
    ],
    "medical_file_no": [
        r"رقم\s*الملف(?:\s*الطبي)?", r"ملف\s*رقم", r"(?:medical\s*)?(?:file|record|mrn)\s*(?:no\.?|number)?",
        r"\bmrn\b", r"hospital\s*(?:file|no\.?)",
    ],
    "registry_no": [
        r"رقم\s*السجل", r"سجل\s*رقم", r"registry\s*(?:no\.?|number|id|accession)", r"accession",
    ],
    "first_name": [r"الاسم\s*الاول", r"الاسم\s*الأول", r"\bfirst\s*name\b", r"given\s*name"],
    "father_name": [r"اسم\s*الاب", r"اسم\s*الأب", r"father(?:'s)?\s*name"],
    "grandfather_name": [r"اسم\s*الجد", r"grandfather"],
    "family_name": [r"اسم\s*العائلة", r"اللقب", r"الاسم\s*الاخير", r"(?:family|last|sur)\s*name"],
    "full_name": [
        r"الاسم\s*الثلاثي", r"الاسم\s*الرباعي", r"اسم\s*المريض(?:ة)?", r"الاسم\s*(?:الكامل)?",
        r"(?:patient\s*)?(?:full\s*)?name", r"\bpatient\b",
    ],
    "sex": [r"الجنس", r"النوع", r"\bsex\b", r"\bgender\b"],
    "birth_date": [
        r"تاريخ\s*الميلاد", r"ميلاد", r"تاريخ\s*الولادة", r"date\s*of\s*birth", r"\bdob\b",
        r"birth\s*date",
    ],
    "address": [r"العنوان", r"محل\s*السكن", r"السكن", r"\baddress\b", r"residence"],
    "city": [r"المدينة", r"المحلة", r"\bcity\b", r"locality"],
    "district": [r"البلدية", r"بلدية", r"\bdistrict\b", r"baladiy(?:a|ah)", r"\bmunicipality\b"],
    "phone": [r"الهاتف", r"رقم\s*الهاتف", r"جوال", r"موبايل", r"\bphone\b", r"\bmobile\b", r"\btel\b"],
    "date_of_diagnosis": [
        r"تاريخ\s*(?:اول\s*)?(?:التشخيص|التشخيص\s*الاول)", r"تاريخ\s*التشخيص",
        r"date\s*of\s*diagnosis", r"diagnosis\s*date", r"\bdox\b", r"تاريخ\s*الاثبات",
    ],
    "date_of_first_symptom": [r"تاريخ\s*اول\s*عرض", r"بداية\s*الاعراض", r"date\s*of\s*(?:first\s*)?symptom", r"onset"],
    "primary_site": [
        r"موقع\s*الورم(?:\s*الاولي)?", r"الورم\s*الاولي", r"الموقع\s*الاولي",
        r"primary\s*(?:site|tumou?r\s*site)", r"\btopography\b", r"icd-?o-?3?\s*(?:topography|site)",
    ],
    "morphology": [
        r"الفحص\s*النسيجي", r"التشخيص\s*النسيجي", r"النوع\s*النسيجي", r"المورفولوجيا",
        r"histolog(?:y|ical)\s*(?:type|diagnosis)?", r"\bmorpholog(?:y|ical)\b", r"patholog(?:y|ical)\s*diagnosis",
    ],
    "grade": [r"الدرجة", r"درجة\s*التمايز", r"التمايز", r"\bgrade\b", r"\bdifferentiation\b", r"\bg[1-4]\b"],
    "laterality": [r"الجانبية", r"الجانب\s*(?:الايمن|الأيمن|الايسر|الأيسر|المصاب)?",
                   r"\blaterality\b", r"\bside\s*of\s*(?:tumou?r|lesion)\b"],
    "basis_of_diagnosis": [r"اساس\s*التشخيص", r"طريقة\s*التشخيص", r"basis\s*of\s*diagnosis", r"\bbod\b"],
    "staging_system": [r"نظام\s*التقسيم", r"التصنيف\s*المرحلي", r"staging\s*system"],
    "ct": [r"\bc\s*T\b", r"T\s*السريري"],
    "cn": [r"\bc\s*N\b", r"N\s*السريري"],
    "cm": [r"\bc\s*M\b", r"M\s*السريري"],
    "pt": [r"\bp\s*T\b", r"T\s*النسيجي"],
    "pn": [r"\bp\s*N\b", r"N\s*النسيجي"],
    "pm": [r"\bp\s*M\b", r"M\s*النسيجي"],
    "clinical_stage": [r"المرحلة\s*السريرية", r"clinical\s*stage", r"\bcstage\b"],
    "pathological_stage": [r"المرحلة\s*النسيجية", r"patholog(?:ical)?\s*stage", r"\bpstage\b"],
    "summary_stage": [r"المرحلة\s*الموجزة", r"summary\s*stage"],
    "vitality_status": [
        r"حالة\s*المريض", r"حالة\s*الحالة", r"الوضع\s*الحالي", r"على\s*قيد\s*الحياة",
        r"vital\s*status", r"patient\s*status", r"follow-?up\s*status", r"alive\s*/\s*dead",
    ],
    "date_of_death": [r"تاريخ\s*الوفاة", r"الوفاة\s*بتاريخ", r"date\s*of\s*death", r"\bdod\b", r"deceased\s*on"],
    "cause_of_death": [r"سبب\s*الوفاة", r"cause\s*of\s*death", r"underlying\s*cause"],
    "last_followup_date": [r"اخر\s*متابعة", r"آخر\s*متابعة", r"تاريخ\s*اخر\s*متابعة", r"last\s*(?:follow-?up|contact)", r"\blfu\b"],
    "reporting_facility": [r"الجهة\s*المبلغة", r"الجهة\s*المحيلة", r"مصدر\s*الإحالة",
                       r"reporting\s*(?:facility|hospital)", r"referral\s*source",
                       r"\bhospital\b", r"\bالمستشفى\b", r"\bteaching\s+hospital\b"],
    "reporter_name": [r"المبلغ", r"اسم\s*الطبيب", r"notified\s*by", r"reporter"],
    "treatment_summary": [r"ملخص\s*العلاج", r"العلاج\s*المقدم", r"treatment\s*summary", r"therapy\s*given"],
    "risk_factors": [r"عوامل\s*الخطورة", r"risk\s*factors"],
    "family_history": [r"التاريخ\s*العائلي", r"family\s*history"],
    "metastasis_sites": [r"مواقع\s*الانتشار", r"النقائل", r"الانتشار", r"metasta(?:tic\s*sites|ses)"],
    "biomarkers": [r"المؤشرات\s*الحيوية", r"\b(?:er|pr|her2|ki-?67|psa)\b"],
}

# الحقول النصية الحرة التي تأخذ قيمة أطول
MULTIWORD_VALUE = {"address", "full_name", "reporting_facility", "treatment_summary",
                   "metastasis_sites", "biomarkers", "risk_factors", "family_history",
                   "morphology", "city"}

_VALUE_END = r"(?:\n|$|;|\|{2})"

# طى الحروف العربية المتشابهة — التحويل 1:1 لذا تبقى مواضع الأحرف مطابقة
# للنص الأصلى، فنحدد المطابقة فى النص المطوى ثم نقتطع القيمة من النص الأصلى
# (فتبقى «فاطمة» كما هى ولا تتحول إلى «فاطمه»).
_FOLD_MAP = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي",
    "ة": "ه", "ئ": "ي", "ؤ": "و", "ـ": " ",
})


def fold_ar(text: str) -> str:
    """نسخة موحّدة الحروف العربية بنفس الطول والمواضع."""
    return (text or "").translate(_FOLD_MAP)

# علامات حقول أخرى — إذا ظهرت داخل القيمة فالمطابقة تجاوزت حدّها
_NEXT_LABEL = re.compile(
    r"(?<![\u0600-\u06FF])(?:الرقم\s*الوطني|رقم\s*الملف|تاريخ\s*الميلاد|تاريخ\s*التشخيص|تاريخ\s*الوفاة|"
    r"تاريخ\s*التبليغ|اخر\s*متابعة|آخر\s*متابعة|الجنس|النوع|العمر|العنوان|الهاتف|"
    r"البلدية|المدينة|اسم\s*المريض|الاسم\s*الثلاثي|موقع\s*الورم|الفحص\s*النسيجي|"
    r"الجهة\s*المبلغة|المبلغ|حالة\s*المريض|ملخص\s*العلاج|عوامل\s*الخطورة|"
    r"medical\s*record|\bMRN\b|national\s*id|\bDOB\b|\bDOD\b|date\s*of\s*|"
    r"primary\s*site|morpholog|histolog|vital\s*status|treatment\s*summary|"
    r"\bphone\b|\baddress\b|\bsex\b|\bage\b|follow-?up)(?![\u0600-\u06FF])",
    re.IGNORECASE)


def _build_label_rx(aliases, long_value=False) -> re.Pattern:
    # تُطوى التسميات بنفس خريطة النص فتتطابق «الأولي/الاولى» و«البلدية/البلديه»
    alt = "|".join(fold_ar(a) for a in aliases)
    # الفاصل لا يعبر نهاية السطر أبداً — وإلا التهمت القيمة الحقل التالى
    # ملاحظة حرجة: الفاصل يجب أن يكون داخل مجموعة غير لاقطة، وإلا قسّم `|`
    # النمط كله إلى فرعين أحدهما بلا تسمية (فتطابق كل سطر فى المستند).
    sep = r"(?:[ \t]*(?:[:：]|[-–—=]{1,3})[ \t]*|[ \t]+)"
    val = r"([^\n]{1,200}?)" if long_value else r"([^\n]{1,80}?)"
    return re.compile(
        rf"(?:{alt})[ \t]*{sep}[ \t]*{val}{_VALUE_END}",
        re.IGNORECASE | re.MULTILINE,
    )


COMPILED_LABELS = {}
for _fname, _aliases in LABEL_ALIASES.items():
    try:
        COMPILED_LABELS[_fname] = _build_label_rx(_aliases, _fname in MULTIWORD_VALUE)
    except re.error as _exc:                       # pragma: no cover
        COMPILED_LABELS[_fname] = None


# ==========================================================================
#  أنماط خاصة (Pattern miners)
# ==========================================================================

RX_SITE = re.compile(r"\b[Cc](\d{2})(?:[.\-/](\d{1,2}))?\b")
RX_MORPH = re.compile(r"\b(\d{4})\s*[-/\s]\s*([0-369])\b")
RX_NATIONAL_ID = re.compile(r"(?<!\d)(\d{12})(?!\d)")
RX_PHONE = re.compile(r"(?<!\d)(0(?:9[1-6]|2[1-9]|5[1-9]|6[1-9]|7[1-9])\d{7})(?!\d)")
RX_TNM_COMPACT = re.compile(
    r"\b([cp])?\s*T\s*(is|0|[1-4][a-e]?)\s*\(?\w*\)?\s*N\s*(0\(i\+\)|0|[1-3][a-c]?)\s*M\s*(0|1[a-d]?)\b",
    re.IGNORECASE)
RX_TNM_SPACED = re.compile(
    r"\bT\s*(is|0|[1-4][a-e]?)\b[\s,;]*\bN\s*(0|[1-3][a-c]?)\b[\s,;]*\bM\s*(0|1[a-d]?)\b",
    re.IGNORECASE)
RX_STAGE = re.compile(
    r"\b(?:stage|مرحلة|المرحلة)\s*(?:group)?\s*[:\-]?\s*(0|IV|III|II|I)[A-C]?\b",
    re.IGNORECASE)
RX_GRADE = re.compile(r"\b(?:grade|G)\s*[:\-]?\s*([1-4]|x)\b|\b(well|moderately|poorly)\s+differentiated\b|"
                      r"(جيد|متوسط|ضعيف)\s*التمايز", re.IGNORECASE)
RX_AGE = re.compile(r"\b(?:age|العمر|عمر)\s*[:\-]?\s*(\d{1,3})\s*(?:year|سنة|y/?o)?\b", re.IGNORECASE)
RX_CYCLES = re.compile(r"\b(\d{1,2})\s*(?:cycles|دورات|جرعات)\b", re.IGNORECASE)


def _clean_value(v: str, max_len: int = 200) -> str:
    v = (v or "").strip()
    v = re.sub(r"^[:\-\s،,\.]+", "", v).strip()

    # صدى تسمية فى البداية: «المبلغ: د. سامي» → «د. سامي»
    m = re.match(r"^(.{1,40}?)\s*[:：]\s*(.+)$", v)
    if m and _NEXT_LABEL.search(m.group(1)):
        v = m.group(2).strip()

    # «رقم الملف الطبي (MRN): NCI-2024» → احذف الصدى الثنائى اللغة فى البداية
    m = re.match(r"^\(([^)]{1,40})\)\s*[:\-]?\s*(.*)$", v)
    if m:
        rest = m.group(2).strip()
        v = rest if rest else ""

    # اقطع عند أول علامة حقل تالية (تجاوز الحدّ)
    m = _NEXT_LABEL.search(v)
    if m and m.start() > 0:
        v = v[:m.start()]
        # احذف الفواصل المعلّقة
        v = re.sub(r"[\s,،:;.\-–]+$", "", v)

    v = re.sub(r"_{2,}", " ", v)
    v = re.sub(r"\s{2,}", " ", v)
    v = re.sub(r"^[\s,،:;.\-–]+", "", v)
    return v.strip()[:max_len]


# --------------------------------------------------------------------------
#  توحيد القيم المستخرجة إلى مفاتيح القاموس
# --------------------------------------------------------------------------
_ARABIC_ORDINALS = {
    "اول": "1", "أول": "1", "اولى": "1", "أولى": "1", "first": "1", "1st": "1",
    "ثاني": "2", "ثانية": "2", "second": "2", "2nd": "2",
    "ثالث": "3", "ثالثة": "3", "third": "3", "3rd": "3",
    "رابع": "4", "رابعة": "4", "fourth": "4", "4th": "4",
}
_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5}


def _fold_ar(s: str) -> str:
    s = (s or "").lower().strip()
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه"),
                 ("ؤ", "و"), ("ئ", "ي")):
        s = s.replace(a, b)
    return re.sub(r"[\s_\-.,:;()]+", "", s)


def _match_selection(fname: str, raw: str) -> str:
    """يطابق قيمة حرّة مع مفاتيح قائمة الاختيار (عربي/إنجليزي)."""
    from .dictionary import FIELDS
    f = FIELDS.get(fname)
    if not f or not f.get("options"):
        return raw
    opts = f["options"]
    if raw in opts:
        return raw

    fr = _fold_ar(raw)
    if not fr:
        return raw
    best, best_len = "", 0
    for key, (ar, en) in opts.items():
        if _fold_ar(key) == fr:
            return key
        for cand in (ar, en):
            variants = {cand}
            # «6 - تشريح مجهري للورم الأولي» → جرّب أيضاً بدون البادئة الرقمية
            stripped = re.sub(r"^\s*[0-9IVX]+\s*[-–.)]\s*", "", cand or "")
            if stripped:
                variants.add(stripped)
            for c in variants:
                fc = _fold_ar(c)
                if not fc:
                    continue
                if fc == fr:
                    return key
                if len(fc) >= 3 and (fc in fr or fr in fc) and len(fc) > best_len:
                    best, best_len = key, len(fc)
    return best or raw


def _normalise_grade(raw: str) -> str:
    r = (raw or "").strip()
    if re.search(r"not\s+applicable|غير\s*منطبق|لا\s*ينطبق", r, re.I):
        return "9"
    m = re.search(r"\bG\s*([1-9x])\b", r, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    m = re.search(r"\b(1|2|3|4)\b", r)
    if m and len(r) <= 14:
        return m.group(1)
    rom = re.search(r"\b(IV|III|II|I)\b", r.upper())
    if rom and len(r) <= 20:
        return str(min(4, _ROMAN[rom.group(1)]))
    fl = _fold_ar(r)
    for k, v in _ARABIC_ORDINALS.items():
        if _fold_ar(k) in fl:
            return v
    if "جيدالتمايز" in fl and "غير" not in fl:
        return "1"
    if "متوسطالتمايز" in fl:
        return "2"
    if "ضعيفالتمايز" in fl:
        return "3"
    if "غيرمتمايز" in fl or "لاتشكيلي" in fl:
        return "4"
    return _match_selection("grade", r)


def _normalise_stage(raw: str) -> str:
    r = (raw or "").strip()
    m = re.search(r"\b(stage\s*)?(0|IV|III|II|I)\s*([A-C]\d?)?\b", r, re.IGNORECASE)
    if m:
        roman = m.group(2).upper()
        sub = (m.group(3) or "").upper()
        if roman == "0":
            return "Stage 0"
        # IIIA قبل IIA: الترتيب الطويل أولاً
        return f"Stage {roman}{sub}"
    return _match_selection("pathological_stage", r)


def _normalise_tnm(fname: str, raw: str) -> str:
    """
    ct/pt → T…، cn/pn → N…، cm/pm → M…
    يحافظ على المسافات أثناء التحليل لأن «cT2 cN1» بلا مسافات تُقرأ خطأً «T2C».
    """
    letter = fname[-2].upper()                       # T أو N أو M
    prefix = fname[0].lower()                        # c أو p
    v = (raw or "").strip()
    if not v:
        return ""
    # «cT2» / «pN1a» / «T2» / «N1»
    m = re.match(rf"^[cp]?(?:\s|-)?{letter}\s*(is|x|0(?:\(i\+\)|\(mol\+\))?|[1-4][a-e]?|[1-3][a-c]?)$",
                 v, re.IGNORECASE)
    if m:
        return f"{letter}{m.group(1).upper()}"
    # البحث داخل نص أطول: «cT2 cN1 cM0» أو «T2N1M0»
    m = re.search(rf"(?<![A-Za-z0-9]){letter}\s*(is|x|0|[1-4][a-e]?|[1-3][a-c]?)(?![A-Za-z0-9])",
                  v, re.IGNORECASE)
    if m:
        return f"{letter}{m.group(1).upper()}"
    return _match_selection(fname, v)


def normalise_field_value(fname: str, raw) -> str:
    """بوابة التوحيد — تُستدعى لكل قيمة قبل تخزينها."""
    if raw is None:
        return ""
    v = str(raw).strip()
    if not v:
        return ""
    from .dictionary import FIELDS, NOT_APPLICABLE_MAP, NOT_APPLICABLE_RE
    f = FIELDS.get(fname, {})
    t = f.get("type")

    # «Not applicable» / «لا ينطبق» → القيمة الصحيحة لهذه القائمة
    if f.get("type") == "selection" and re.search(NOT_APPLICABLE_RE, v.strip(), re.I):
        na = NOT_APPLICABLE_MAP.get(fname)
        if na and f.get("options") and na in f["options"]:
            return na

    if fname == "grade":
        return _normalise_grade(v)
    if fname in ("clinical_stage", "pathological_stage"):
        return _normalise_stage(v)
    if fname in ("ct", "cn", "cm", "pt", "pn", "pm"):
        return _normalise_tnm(fname, v)
    if fname == "basis_of_diagnosis":
        m = re.match(r"^([0-9])\b", v.strip())
        if m:
            return m.group(1)
        return _match_selection(fname, v)
    if fname == "primary_site":
        return ref.normalise_site(v)
    if fname == "morphology":
        return ref.normalise_morphology(v)
    if fname == "icd10_code":
        return v.strip().upper()
    if t == "selection":
        return _match_selection(fname, v)
    if t == "boolean":
        return "True" if v.lower() in ("true", "1", "yes", "نعم", "y") else \
               ("False" if v.lower() in ("false", "0", "no", "لا", "n") else v)
    if t == "date":
        d = parse_date(v)
        return iso(d) if d else v
    if t in ("integer", "float"):
        m = re.search(r"-?\d+(?:\.\d+)?", v)
        return m.group(0) if m else v
    if fname == "national_id":
        digits = re.sub(r"\D", "", v)
        return digits if len(digits) == 12 else v
    return v


# --------------------------------------------------------------------------
#  تقييم المرشّحين: أي مطابقة للتسمية هي الأرجح؟
# --------------------------------------------------------------------------
def _candidate_score(fname: str, value: str, match) -> int:
    """نقاط أعلى = مطابقة أرجح. الصفر أو أقل = تُرفض."""
    from .dictionary import FIELDS
    f = FIELDS.get(fname, {})
    t = f.get("type", "char")
    score = 0
    matched = match.group(0) if match else ""

    # «الاسم: القيمة» — وجود نقطتين مباشرة بعد التسمية علامة قوية
    if re.search(r"[:：]\s*\S", matched):
        score += 3

    # القيمة تحتوى علامة حقل أخرى → تجاوز حدّ
    if _NEXT_LABEL.search(value):
        score -= 4

    # صدى ثنائى اللغة فقط: «(Treatment Summary)» بدون محتوى
    if re.fullmatch(r"\([^)]{1,60}\)", value.strip()):
        score -= 5

    # طول معقول حسب النوع
    n = len(value)
    if t in ("char", "selection") and n > 60:
        score -= 2
    if t == "date":
        score += 3 if parse_date(value) else -6
    if t == "selection" and f.get("options"):
        score += 3 if _match_selection(fname, value) != value or \
                      _match_selection(fname, value) in f["options"] else -1
    if fname == "national_id":
        digits = re.sub(r"\D", "", value)
        score += 4 if len(digits) == 12 else (1 if 6 <= len(digits) < 12 else -3)
    if fname == "phone":
        score += 2 if len(re.sub(r"\D", "", value)) >= 9 else -3
    if fname in ("ct", "cn", "cm", "pt", "pn", "pm"):
        letter = fname[-2].upper()
        ok = re.fullmatch(rf"[cp]?\s*{letter}\s*(?:is|x|0|[1-4][a-e]?|[1-3][a-c]?)",
                          value.strip(), re.IGNORECASE)
        score += 4 if ok else -5
    if fname == "primary_site":
        score += 4 if re.match(r"^C\d{2}(\.\d{1,2})?$", value.strip().upper()) else -3
    if fname == "morphology":
        score += 4 if re.match(r"^\d{4}\s*[-/]\s*[0-369]$", value.strip()) else -3
    if fname in ("grade", "clinical_stage", "pathological_stage"):
        score += 2
    if n <= 2:
        score -= 2
    return score


def _looks_like_placeholder(v: str) -> bool:
    """قيم شائعة تعني «غير متوفر» — لا تُخزَّن كقيمة."""
    if not v:
        return True
    lv = v.lower().strip()
    junk = {"", "-", "--", "---", ".", "..", "n/a", "na", "nil", "null",
            "لا يوجد", "لايوجد", "غير متوفر", "-", "؟", "?", "/", "x", "xx",
            "______", "………", "..."}
    # ملاحظة: «unknown» و«غير معروف» قيم معتمدة فى القاموس فلا تُعامل كفراغ
    if lv in junk:
        return True
    if re.fullmatch(r"[\s_\-\.…،,/\\?؟]+", v):
        return True
    return False


# ==========================================================================
#  نتيجة الاستخراج
# ==========================================================================
@dataclass
class FieldHit:
    name: str
    value: str
    confidence: float
    method: str          # label | pattern | derived | none
    evidence: str = ""   # المقطع الأصلي من المستند


@dataclass
class ExtractionResult:
    values: dict = dc_field(default_factory=dict)
    hits: dict = dc_field(default_factory=dict)       # name -> FieldHit
    ocr_confidence: float = 0.0
    engine: str = "none"
    warnings: list = dc_field(default_factory=list)
    text: str = ""

    def set(self, name, value, confidence, method, evidence=""):
        """يكتب قيمة فقط إذا كانت أفضل مما هو موجود (ثقة أعلى)."""
        if value is None:
            return
        v = str(value).strip()
        if not v:
            return
        try:
            v = normalise_field_value(name, v) or v
        except Exception:                      # pragma: no cover
            pass
        if _looks_like_placeholder(v):
            return
        prev = self.hits.get(name)
        if prev and prev.confidence >= confidence:
            return
        self.values[name] = v
        self.hits[name] = FieldHit(name, v, confidence, method, evidence[:220])

    @property
    def overall_confidence(self) -> float:
        """متوسط مرجّح: 60% ثقة OCR + 40% متوسط ثقة الحقول المستخرجة."""
        field_conf = ([h.confidence for h in self.hits.values()] or [0])
        avg = sum(field_conf) / len(field_conf)
        return round(0.6 * self.ocr_confidence + 0.4 * (avg * 100), 1)

    @property
    def filled(self) -> list:
        return sorted(self.values.keys())

    def to_dict(self):
        return {
            "values": self.values,
            "hits": {k: vars(v) for k, v in self.hits.items()},
            "confidence": self.overall_confidence,
            "engine": self.engine,
            "warnings": self.warnings,
            "filled": [k for k in self.values if not k.startswith("_")],
            "filled_count": len([k for k in self.values if not k.startswith("_")]),
            "text": self.text[:20000],
        }


# ==========================================================================
#  استخراج الكتل السردية (حقول محتواها على عدة أسطر)
# ==========================================================================
BLOCK_FIELDS = {
    "treatment_summary": [r"ملخص\s*العلاج", r"العلاج\s*المقدم", r"treatment\s*summary",
                          r"therapy\s*given", r"plan\s*of\s*treatment"],
    "biomarkers":        [r"المؤشرات\s*الحيوية", r"biomarkers", r"immunohistochemistry",
                          r"\bIHC\b", r"receptor\s*status"],
    "risk_factors":      [r"عوامل\s*الخطورة", r"risk\s*factors", r"predisposing"],
    "family_history":    [r"التاريخ\s*العائلي", r"family\s*history"],
    "metastasis_sites":  [r"مواقع\s*الانتشار", r"النقائل", r"metastatic\s*sites",
                          r"metastases"],
    "histology_text":    [r"الفحص\s*النسيجي", r"التشخيص\s*النسيجي", r"النوع\s*النسيجي",
                          r"histopatholog\w*\s*diagnosis", r"patholog\w*\s*diagnosis",
                          r"final\s*diagnosis"],
}

BLOCK_LINES = {"treatment_summary": 16, "biomarkers": 6, "risk_factors": 4,
               "family_history": 3, "metastasis_sites": 4, "histology_text": 5}

_SEPARATOR_LINE = re.compile(r"^\s*[=\-*─—_~]{3,}\s*$")


_LEAD_TRIM = re.compile(r"^\s*(?:\([^)]*\))?\s*[:：\-–—]?\s*")
_TRAIL_LABEL_LINE = re.compile(
    r"^\s*(?:الرقم|تاريخ|الاسم|اسم|الجنس|العمر|العنوان|الهاتف|البلدية|المدينة|"
    r"اساس|أساس|موقع|الفحص|الدرجة|الجانبية|حالة|ملخص|عوامل|التاريخ|اخر|آخر|عدد|"
    r"medical|national|date|name|sex|age|address|phone|district|city|"
    r"basis|primary|morpholog|histolog|grade|laterality|vital|treatment|"
    r"follow|report|notif)\b", re.IGNORECASE)


def _extract_block(text: str, anchors: list, max_lines: int = 8):
    """
    يعيد (الكتلة، الدليل) أو None.

    التقارير الطبية تضع العنوان ثم خطاً فاصلاً ثم المحتوى:
        ملخص العلاج (Treatment Summary)
        ----------------------------------------------------
        1) جراحة: ...
    لذا نتجاهل فاصلاً واحداً في البداية، ونتوقف عند الفاصل التالي.
    """
    lines = text.split("\n")
    best = None
    for anc in anchors:
        for i, line in enumerate(lines):
            m = re.search(fold_ar(anc), fold_ar(line), re.IGNORECASE)
            if not m:
                continue
            rest = _LEAD_TRIM.sub("", line[m.end():]).strip()
            rest = re.sub(r"^[\)\]\}\s،,.:;\-–—]+", "", rest).strip()

            collected = []
            if len(rest) >= 6 and not _NEXT_LABEL.search(rest) and not re.fullmatch(r"[\W_]+", rest):
                collected.append(rest)

            skipped_sep, blanks = False, 0
            for j in range(i + 1, min(i + 1 + max_lines, len(lines))):
                nxt = lines[j]
                stripped = nxt.strip()

                if _SEPARATOR_LINE.match(nxt):
                    if not collected and not skipped_sep:
                        skipped_sep = True          # فاصل العنوان → تجاوزه
                        continue
                    break                           # فاصل بعد المحتوى → نهاية الكتلة
                if not stripped:
                    blanks += 1
                    if collected and blanks >= 2:
                        break
                    continue
                if _TRAIL_LABEL_LINE.match(stripped) and re.search(r"[:：]", stripped[:45]):
                    break
                if _NEXT_LABEL.search(stripped) and re.search(r"[:：]", stripped):
                    break
                collected.append(stripped)
                blanks = 0

            body = " ".join(collected).strip()
            body = re.sub(r"\s{2,}", " ", body)
            if len(body) < 10 or re.fullmatch(r"[\W_]+", body):
                continue
            evidence = "\n".join(lines[i:min(i + 5, len(lines))])
            if best is None or len(body) > len(best[0]):
                best = (body[:600], evidence)
    return best


# ==========================================================================
#  المحرّك الرئيسي
# ==========================================================================

SEX_HINTS_F = ["انثى", "أنثى", "سيدة", "مريضة", "female", "f", "woman", "female patient"]
SEX_HINTS_M = ["ذكر", "رجل", "مريض", "male", "m", "man", "gentleman"]
ALIVE_HINTS = ["على قيد الحياة", "حي", "حية", "alive", "living", "awd", "ned"]
DEAD_HINTS = ["متوفي", "متوفى", "متوفيه", "متوفاة", "وفاة", "توفي", "توفيت", "deceased",
              "dead", "died", "expired", "death", "dod"]
LOST_HINTS = ["مفقود المتابعة", "فقد المتابعة", "lost to follow", "ltfu", "defaulted"]


def extract(raw_text: str, engine: str = "none", ocr_confidence: float = 0.0,
            hints: Optional[dict] = None) -> ExtractionResult:
    """
    يستخرج كل الحقول الممكنة من نص التقرير.

    hints: بيانات معروفة مسبقاً (مثل اسم الملف أو بيانات المريض من القائمة)
           تُستخدم لرفع دقة استخراج الاسم.
    """
    res = ExtractionResult(engine=engine, ocr_confidence=ocr_confidence)
    if not raw_text or not raw_text.strip():
        res.warnings.append("لا يوجد نص للاستخراج")
        return res

    text = normalise_text(raw_text)
    ftext = fold_ar(text)          # نسخة مطوية بنفس المواضع — للبحث عن التسميات
    res.text = text
    hints = hints or {}

    # -------------------------------------------------- 1) التسميات
    for fname, rx in COMPILED_LABELS.items():
        if rx is None:
            continue
        cands = []
        for m in rx.finditer(ftext):
            s0, s1 = m.span(1)
            raw = _clean_value(text[s0:s1])      # القيمة من النص الأصلى غير المطوى
            if _looks_like_placeholder(raw):
                continue
            cands.append((raw, m))
        if not cands:
            continue
        best_raw, best_m = max(cands, key=lambda c: _candidate_score(fname, c[0], c[1]))
        score = _candidate_score(fname, best_raw, best_m)
        if score <= 0:
            continue
        conf = min(0.9, 0.6 + 0.05 * score)
        e0, e1 = best_m.span()
        res.set(fname, best_raw, conf, "label", text[e0:e1])

    # -------------------------------------------------- 1ب) الكتل السردية
    # حقول مثل «ملخص العلاج» و«المؤشرات الحيوية» محتواها فى الأسطر التالية للتسمية
    for fname, anchors in BLOCK_FIELDS.items():
        block = _extract_block(text, anchors, max_lines=BLOCK_LINES.get(fname, 8))
        if block:
            res.set(fname, block[0], 0.62, "label+block", block[1])

    # -------------------------------------------------- 2) الأنماط
    m = RX_SITE.search(text)
    if m:
        code = ref.normalise_site(f"C{m.group(1)}" + (f".{m.group(2)}" if m.group(2) else ""))
        if ref.is_valid_site(code):
            res.set("primary_site", code, 0.95, "pattern", m.group(0))

    m = RX_MORPH.search(text)
    if m:
        code = ref.normalise_morphology(f"{m.group(1)}/{m.group(2)}")
        if ref.is_valid_morphology(code):
            res.set("morphology", code, 0.95, "pattern", m.group(0))

    m = RX_NATIONAL_ID.search(text)
    if m:
        res.set("national_id", m.group(1), 0.9, "pattern", m.group(0))

    m = RX_PHONE.search(text)
    if m:
        res.set("phone", m.group(1), 0.85, "pattern", m.group(0))

    # TNM
    tnm = RX_TNM_COMPACT.search(text) or RX_TNM_SPACED.search(text)
    if tnm:
        groups = [g for g in tnm.groups() if g]
        prefix = ""
        vals = groups
        if tnm.re is RX_TNM_COMPACT:
            prefix = (tnm.group(1) or "").lower()
            vals = [tnm.group(2), tnm.group(3), tnm.group(4)]
        t, n, mm = [v.upper() if v else "" for v in vals[:3]]
        t = f"T{t}" if t and not t.upper().startswith("T") else t
        n = f"N{n}" if n and not n.upper().startswith("N") else n
        mm = f"M{mm}" if mm and not mm.upper().startswith("M") else mm
        res.set("pt" if prefix == "p" else "ct", t, 0.9, "pattern", tnm.group(0))
        res.set("pn" if prefix == "p" else "cn", n, 0.9, "pattern", tnm.group(0))
        res.set("pm" if prefix == "p" else "cm", mm, 0.9, "pattern", tnm.group(0))

    m = RX_STAGE.search(text)
    if m:
        stage = "Stage " + m.group(1).upper()
        if stage == "Stage 0":
            stage = "Stage 0"
        res.set("pathological_stage", stage, 0.7, "pattern", m.group(0))

    m = RX_AGE.search(text)
    if m:
        res.set("age_at_diagnosis", m.group(1), 0.8, "pattern", m.group(0))

    # -------------------------------------------------- 3) التواريخ
    date_fields = [
        ("date_of_diagnosis", [
            r"تاريخ\s*(?:اول\s*)?التشخيص", r"date\s*of\s*diagnosis", r"diagnosis\s*date",
            r"تاريخ\s*الاثبات", r"تشخيص\s*بتاريخ", r"\bdox\b"]),
        ("birth_date", [r"تاريخ\s*الميلاد", r"date\s*of\s*birth", r"\bdob\b", r"ميلاد\s*:"]),
        ("date_of_death", [r"تاريخ\s*الوفاة", r"date\s*of\s*death", r"\bdod\b", r"توفي\s*(?:بتاريخ)?"]),
        ("last_followup_date", [r"اخر\s*متابعة", r"آخر\s*متابعة", r"last\s*follow-?up", r"\blfu\b"]),
        ("notification_date", [r"تاريخ\s*التبليغ", r"date\s*of\s*notification"]),
        ("stage_date", [r"تاريخ\s*التقسيم", r"staging\s*date"]),
    ]
    for fname, anchors in date_fields:
        best = None
        for anc in anchors:
            rx = re.compile(fold_ar(anc) + r"[ \t]*[:\-]?[ \t]*([^\n]{0,40})", re.IGNORECASE)
            for m in rx.finditer(ftext):
                s0, s1 = m.span(1)
                d = parse_date(text[s0:s1]) or parse_date(text[m.start():m.end()])
                if d:
                    best = (d, text[m.start():m.end()])
                    break
            if best:
                break
        if best:
            res.set(fname, iso(best[0]), 0.88, "label", best[1])

    # تاريخ تشخيص احتياطي: أول تاريخ منطقي في المستند
    if "date_of_diagnosis" not in res.values:
        for m in re.finditer(r"\b\d{1,2}[-/.]\d{1,2}[-/.](?:20|19)\d{2}\b|"
                             r"\b(?:20|19)\d{2}[-/.]\d{1,2}[-/.]\d{1,2}\b", text):
            d = parse_date(m.group(0))
            if d and 1930 <= d.year <= date.today().year:
                res.set("date_of_diagnosis", iso(d), 0.4, "pattern", m.group(0))
                res.warnings.append("تاريخ التشخيص مُستنتج من أول تاريخ في المستند — يحتاج مراجعة")
                break

    # -------------------------------------------------- 4) الجنس
    low = text.lower()
    if "sex" in res.values:
        res.values["sex"] = _map_sex(res.values["sex"])
        res.hits["sex"].value = res.values["sex"]
    else:
        score_f = sum(1 for h in SEX_HINTS_F if h in low or h in text)
        score_m = sum(1 for h in SEX_HINTS_M if h in low or h in text)
        # ألقاب عربية في الاسم
        if re.search(r"(سعاد|فاطمه|عائشه|مريم|خديجه|امنه|زينب|سالمه|نعيمه|هدي|هدى|امل|سناء|انتصار|سلمي)", ftext):
            score_f += 2
        if re.search(r"(محمد|احمد|علي|عمر|خالد|يوسف|ابراهيم|مصطفي|فتحي|صلاح|سامي|نبيل|عبد\s*الله)", ftext):
            score_m += 1
        if score_f > score_m:
            res.set("sex", "female", min(0.6, 0.3 * score_f), "pattern", "استنتاج من السياق")
        elif score_m > score_f:
            res.set("sex", "male", min(0.6, 0.3 * score_m), "pattern", "استنتاج من السياق")

    # -------------------------------------------------- 5) حالة الحياة
    has_dead = any(h in text or h in low for h in DEAD_HINTS)
    has_alive = any(h in text or h in low for h in ALIVE_HINTS)
    has_lost = any(h in text or h in low for h in LOST_HINTS)
    if has_lost:
        res.set("vitality_status", "lost", 0.8, "pattern", "مفقود المتابعة")
    elif has_dead:
        cause = "dead_cancer" if re.search(r"(بسبب\s*الورم|بسبب\s*السرطان|cancer[- ]related|due\s+to\s+(?:the\s+)?(?:cancer|tumou?r|malignancy))", text, re.I) else "dead"
        res.set("vitality_status", cause, 0.85, "pattern", "وفاة")
    elif has_alive:
        res.set("vitality_status", "alive", 0.7, "pattern", "على قيد الحياة")

    if res.values.get("date_of_death") and not res.values.get("vitality_status", "").startswith("dead"):
        res.set("vitality_status", "dead", 0.8, "derived", "يوجد تاريخ وفاة")

    # -------------------------------------------------- 6) اشتقاقات
    _derive(res, text, hints)

    # -------------------------------------------------- 7) العلاج
    _extract_treatment(res, text)

    return res


def _map_sex(raw: str) -> str:
    r = (raw or "").strip().lower()
    if r in ("m", "male", "ذكر", "رجل", "1"):
        return "male"
    if r in ("f", "female", "انثى", "أنثى", "سيدة", "2"):
        return "female"
    if "ذكر" in r or "male" in r:
        return "male"
    if "انث" in r or "أنث" in r or "female" in r:
        return "female"
    return raw


# --------------------------------------------------------------------------
HONORIFICS = {"د.", "دكتور", "دكتورة", "سيد", "سيدة", "الآنسة", "الانسة", "م.", "مهندس",
              "أ.", "أستاذ", "mr", "mrs", "ms", "miss", "dr", "dr.", "prof", "prof.",
              "sir", "madam", "المرحوم", "المرحومة"}

NAME_PARTICLES_AR = {"بن", "ابن", "أبو", "ابو", "آل", "ال", "ابي", "أبي"}
NAME_PARTICLES_EN = {"al-", "el-", "ben", "abu", "bin", "ibn", "van", "de", "del"}


def split_person_name(full_name: str) -> dict:
    """
    يقسّم الاسم الكامل إلى (أول، أب، جد، عائلة).

    يعتني بـ:
      • الألقاب: د.، سيد، Dr …
      • الروابط العربية: بن / ابن / أبو / آل
      • الروابط اللاتينية: Al- / Bin / Abu
    """
    out = {"first_name": "", "father_name": "", "grandfather_name": "", "family_name": ""}
    if not full_name:
        return out
    tokens = [t for t in re.split(r"\s+", full_name.strip()) if t]
    tokens = [t for t in tokens if t.strip(".,:;") not in HONORIFICS]
    if not tokens:
        return out

    # ادمج الرابط مع ما بعده («بن علي» → وحدة واحدة، «Al-Mabrouk» كما هى)
    merged, i = [], 0
    while i < len(tokens):
        t = tokens[i]
        low = t.lower()
        if (t in NAME_PARTICLES_AR or low in NAME_PARTICLES_EN) and i + 1 < len(tokens):
            merged.append(f"{t} {tokens[i + 1]}")
            i += 2
            continue
        merged.append(t)
        i += 1
    tokens = merged

    n = len(tokens)
    if n == 1:
        out["first_name"] = tokens[0]
    elif n == 2:
        out["first_name"], out["family_name"] = tokens
    elif n == 3:
        out["first_name"], out["father_name"], out["family_name"] = tokens
    else:
        out["first_name"] = tokens[0]
        out["father_name"] = tokens[1]
        out["grandfather_name"] = tokens[2]
        out["family_name"] = " ".join(tokens[3:])
    return out


def _derive(res: ExtractionResult, text: str, hints: dict) -> None:
    """الطبقة الثالثة: اشتقاق الحقول المحسوبة من الحقول المستخرجة."""
    v = res.values

    # الاسم الكامل من الأجزاء
    if "full_name" not in v:
        parts = [v.get(k, "") for k in ("first_name", "father_name",
                                        "grandfather_name", "family_name")]
        joined = " ".join(p for p in parts if p)
        if joined:
            res.set("full_name", joined, 0.9, "derived", "مجمّع من أجزاء الاسم")

    # العكس: تقسيم الاسم الكامل إلى أجزائه (شائع — التقارير تكتب الاسم كاملاً فقط)
    if v.get("full_name") and not v.get("first_name"):
        split = split_person_name(v["full_name"])
        for k, val in split.items():
            if val:
                res.set(k, val, 0.5, "derived", f"تقسيم آلي للاسم: {v['full_name']}")
        if any(split.values()):
            res.set("_name_split_auto", "True", 1.0, "derived", "")

    # تسميات ICD-O-3
    if v.get("primary_site"):
        code = ref.normalise_site(v["primary_site"])
        v["primary_site"] = code
        lbl = ref.site_label(code, "ar")
        if lbl:
            res.set("primary_site_label", lbl, 0.99, "derived", f"ICD-O-3 {code}")

    if v.get("morphology"):
        code = ref.normalise_morphology(v["morphology"])
        v["morphology"] = code
        lbl = ref.morphology_label(code, "ar")
        if lbl:
            res.set("morphology_label", lbl, 0.99, "derived", f"ICD-O-3 {code}")
        beh = ref.behaviour_from_morphology(code)
        if beh in ("0", "1", "2", "3", "6", "9"):
            res.set("behaviour", beh, 0.99, "derived", f"السلوك من {code}")

    # ICD-10
    if v.get("primary_site"):
        icd10 = ref.icd10_from_icdo3(v["primary_site"])
        if icd10:
            res.set("icd10_code", icd10, 0.9, "derived",
                    f"تحويل ICD-O-3 {v['primary_site']} → ICD-10")

    # العمر عند التشخيص
    dob = parse_date(v.get("birth_date"))
    dod = parse_date(v.get("date_of_diagnosis"))
    if dob and dod:
        age = dod.year - dob.year - ((dod.month, dod.day) < (dob.month, dob.day))
        if 0 <= age <= 120:
            res.set("age_at_diagnosis", str(age), 0.98, "derived",
                    f"{iso(dod)} − {iso(dob)}")
    if dod:
        res.set("diagnosis_year", str(dod.year), 0.99, "derived", iso(dod))

    # TNM: استخدم النسيجي إن وُجد وإلا السريري
    t = v.get("pt") or v.get("ct") or ""
    n = v.get("pn") or v.get("cn") or ""
    m = v.get("pm") or v.get("cm") or ""
    if t or n or m:
        if not v.get("pathological_stage"):
            sg = ref.derive_stage_group(v.get("primary_site", ""), t, n, m)
            if sg:
                res.set("pathological_stage", sg, 0.85, "derived", f"{t} {n} {m}")
        if not v.get("clinical_stage") and v.get("ct"):
            sg = ref.derive_stage_group(v.get("primary_site", ""),
                                        v.get("ct", ""), v.get("cn", ""), v.get("cm", ""))
            if sg:
                res.set("clinical_stage", sg, 0.75, "derived", "TNM سريري")
        ss = ref.summary_stage_from_tnm(t, n, m)
        if ss and ss != "unknown":
            res.set("summary_stage", ss, 0.8, "derived", f"{t} {n} {m}")
        if not v.get("staging_system"):
            res.set("staging_system", "ajcc8", 0.5, "derived", "افتراضي AJCC 8th")

    # /2 = in situ → المرحلة الموجزة
    if v.get("behaviour") == "2":
        res.set("summary_stage", "in_situ", 0.85, "derived", "سلوك /2 = لابِد")

    # مدة البقاء
    start = parse_date(v.get("date_of_diagnosis"))
    end = parse_date(v.get("date_of_death")) or parse_date(v.get("last_followup_date"))
    if start and end and end >= start:
        months = (end.year - start.year) * 12 + (end.month - start.month)
        res.set("survival_months", str(months), 0.95, "derived",
                f"{iso(end)} − {iso(start)}")

    # العمر عند الوفاة
    if dob and parse_date(v.get("date_of_death")):
        dd = parse_date(v["date_of_death"])
        res.set("death_age", str(dd.year - dob.year - ((dd.month, dd.day) < (dob.month, dob.day))),
                0.95, "derived", "")

    # سبب الوفاة
    if str(v.get("vitality_status", "")).startswith("dead") and not v.get("cause_of_death"):
        if re.search(r"(بسبب\s*الورم|بسبب\s*السرطان|cancer[- ]related|due\s+to\s+(?:cancer|tumou?r|malignancy))", text, re.I):
            res.set("cause_of_death", "cancer", 0.7, "pattern", "سبب الوفاة: الورم")
        else:
            res.set("cause_of_death", "unknown", 0.4, "derived", "افتراضي — يحتاج توثيق")

    # الدرجة
    mg = RX_GRADE.search(text)
    if mg and not v.get("grade"):
        g = (mg.group(1) or "").upper()
        if g in "1234":
            res.set("grade", g, 0.8, "pattern", mg.group(0))
        else:
            word = (mg.group(2) or mg.group(3) or "").lower()
            mapping = {"well": "1", "جيد": "1", "moderately": "2", "متوسط": "2",
                       "poorly": "3", "ضعيف": "3"}
            for k, val in mapping.items():
                if k in word:
                    res.set("grade", val, 0.75, "pattern", mg.group(0))
                    break

    # أساس التشخيص
    if not v.get("basis_of_diagnosis"):
        if re.search(r"(histopatholog|histolog|نسيجي|خزعة|biopsy|تشريح\s*مرضي)", text, re.I):
            res.set("basis_of_diagnosis", "6", 0.8, "pattern", "تشريح مجهري للورم الأولي")
        elif re.search(r"(cytolog|سيتولوجي|خلايا|fnac|fine\s*needle|شفط)", text, re.I):
            res.set("basis_of_diagnosis", "5", 0.75, "pattern", "سيتولوجيا")
        elif re.search(r"(mammogra|اشعة|أشعة|اشعاع|x-?ray|ct\s*scan|تصوير|ultrasound|ultra\s*sound|سونار|mri|radiolog)", text, re.I):
            res.set("basis_of_diagnosis", "2", 0.6, "pattern", "تصوير/تنظير")
        elif re.search(r"(clinical|سريري|فحص\s*سريري)", text, re.I):
            res.set("basis_of_diagnosis", "1", 0.5, "pattern", "سريري")

    # الجانبية
    if not v.get("laterality"):
        if re.search(r"(ثنائي|bilateral|both\s+(?:breast|kidney|lung|testis|ovar))", text, re.I):
            res.set("laterality", "4", 0.75, "pattern", "ثنائي الجانب")
        elif re.search(r"(ايمن|أيمن|right|الجهة\s*اليمنى|right-?sided)", text, re.I):
            res.set("laterality", "1", 0.75, "pattern", "أيمن")
        elif re.search(r"(ايسر|أيسر|يسار|left|الجهة\s*اليسرى|left-?sided)", text, re.I):
            res.set("laterality", "2", 0.75, "pattern", "أيسر")
        elif re.search(r"(خط\s*الوسط|midline)", text, re.I):
            res.set("laterality", "5", 0.7, "pattern", "خط الوسط")

    # مركز العلاج / الجهة المبلّغة — من ترويسة المستند عند غياب التسمية الصريحة
    for fname in ("reporting_facility", "treatment_centre"):
        if v.get(fname):
            continue
        from .dictionary import TREATMENT_CENTRES
        ranked = sorted(TREATMENT_CENTRES.items(), key=lambda kv: -len(kv[1][1]))
        for key, (ar, en) in ranked:
            if key in ("other", "unknown", "private", "abroad"):
                continue
            if (en and re.search(re.escape(en), text, re.IGNORECASE)) or (ar and ar in text):
                if fname == "treatment_centre":
                    res.set(fname, key, 0.55, "pattern", f"ورد «{en or ar}» في المستند")
                else:
                    res.set(fname, en or ar, 0.55, "pattern", f"ورد «{en or ar}» في الترويسة")
                break

    # البلدية — بحث احتياطى بحدود كلمة عربية (حتى لا يلتقط «الطرابلسي» ← طرابلس)
    if not v.get("district"):
        from .dictionary import LIBYA_DISTRICTS
        ranked = sorted(LIBYA_DISTRICTS.items(), key=lambda kv: -len(kv[1][0]))
        for key, (ar, _en) in ranked:
            rx = re.compile(rf"(?<![\u0600-\u06FF]){re.escape(ar)}(?![\u0600-\u06FF])")
            m = rx.search(text)
            if m:
                res.set("district", key, 0.6, "pattern", f"وردت «{ar}» في المستند")
                break


# --------------------------------------------------------------------------
_AR = r"\u0600-\u06FF"
NEGATION = re.compile(
    rf"(?:\bnot\b|\bno\b|\bnone\b|\bn/?a\b|\bnegative\b|\bnot\s+given\b|\bnot\s+applicable\b|"
    rf"\bdenied\b|\brefused\b|\bnever\b|\bdid\s+not\b|\bwas\s+not\b|\bwithout\b|\bnil\b|"
    rf"(?<![{_AR}])(?:لا|لم|ما|غير\s*معط[اي]|غير\s*مطبق|لم\s*يُ?عط|لم\s*يتم|لا\s*ينطبق|"
    rf"مرفوض|بدون|لم\s*ياخذ|لم\s*يأخذ|ليس\s*موجود)(?![{_AR}]))",
    re.IGNORECASE)


def _is_negated(text: str, start: int, window: int = 60) -> bool:
    """يتحقق هل الدليل منفيّ: «Radiotherapy: NOT given», «علاج هرموني: لا»."""
    left = text[max(0, start - window):start]
    right = text[start:start + window]
    # النفي قبل الكلمة مباشرة أو بعدها مباشرة (النمط الشائع «X: NOT given»)
    near_right = re.match(r"[\s:،,\-–—]*(\S+[\s\S]{0,25})", right)
    if NEGATION.search(left[-28:]) or (near_right and NEGATION.search(near_right.group(0)[:26])):
        return True
    return False


def _extract_treatment(res: ExtractionResult, text: str) -> None:
    """يكتشف أنواع العلاج من النص ويضع أعلاماً منطقية + ملخصاً."""
    patterns = {
        "surgery_performed": [
            (r"(mastectomy|استئصال\s*(?:الثدي|الورم)|lumpectomy|wide\s*local\s*excision|"
             r"radical\s*(?:resection|surgery)|surgery|عملية\s*جراحية|جراحة|"
             r"hysterectomy|استئصال\s*الرحم|prostatectomy|استئصال\s*البروستات|"
             r"colectomy|استئصال\s*القولون|lobectomy|استئصال\s*فص|gastrectomy|"
             r"nephrectomy|استئصال\s*الكلية|TURBT|ورقية|excision|استئصال)", 0.8),
        ],
        "chemotherapy_given": [
            (r"(chemotherapy|علاج\s*كيميائي|كيماوي|كيمائي|adriamycin|cisplatin|carboplatin|"
             r"paclitaxel|docetaxel|5-?fu|fluorouracil|cyclophosphamide|doxorubicin|"
             r"methotrexate|gemcitabine|oxaliplatin|irinotecan|etoposide|vincristine|"
             r"\bAC\b|\bFOLFOX\b|\bCHOP\b|\bR-CHOP\b|\bTCH\b|\bABVD\b|بروتوكول|دورات)", 0.85),
        ],
        "radiotherapy_given": [
            (r"(radiotherapy|radiation\s*therapy|علاج\s*إ?شعاعي|اشعاع|أشعة|irradiation|"
             r"\bEBRT\b|\bIMRT\b|\bVMAT\b|\bSBRT\b|cobalt|كوبالت|خطي\s*معجل|linear\s*accelerator|"
             r"brachytherapy|علاج\s*قريب|gray|\bGy\b|إ?شعاع[يي]|شعاعي)", 0.85),
        ],
        "hormonal_given": [
            (r"(hormonal?\s*therapy|علاج\s*هرموني|tamoxifen|تاموكسيفين|letrozole|ليتروزول|"
             r"anastrozole|anastrazole|exemestane|goserelin|zoladex|bicalutamide|abiraterone|"
             r"leuprolide)", 0.85),
        ],
        "immunotherapy_given": [
            (r"(immunotherapy|علاج\s*مناعي|pembrolizumab|nivolumab|atezolizumab|trastuzumab|"
             r"هيرسبتين|herceptin|rituximab|bevacizumab|targeted\s*therapy|علاج\s*موجه|"
             r"علاج\s*مستهدف|imatinib)", 0.85),
        ],
    }
    for fname, rules in patterns.items():
        found, negated_ev = False, ""
        for rx, conf in rules:
            for m in re.finditer(rx, text, re.IGNORECASE):
                if _is_negated(text, m.start()):
                    negated_ev = negated_ev or m.group(0)
                    continue
                res.set(fname, "True", conf, "pattern", m.group(0))
                found = True
                break
            if found:
                break
        if not found and negated_ev:
            res.set(fname, "False", 0.72, "pattern", f"منفيّ صراحةً: «{negated_ev}»")

    # ملخص سردي للعلاج
    if not res.values.get("treatment_summary"):
        lines = []
        for fname, label in [
            ("surgery_performed", "جراحة"),
            ("chemotherapy_given", "علاج كيميائي"),
            ("radiotherapy_given", "علاج إشعاعي"),
            ("hormonal_given", "علاج هرموني"),
            ("immunotherapy_given", "علاج مناعي/موجّه"),
        ]:
            if str(res.values.get(fname, "")).lower() in ("true", "1", "yes"):
                h = res.hits.get(fname)
                lines.append(f"{label} (الدليل: {h.evidence[:60]})" if h else label)
        if lines:
            res.set("treatment_summary", "؛ ".join(lines), 0.6, "derived", "استخراج آلي")

    mc = RX_CYCLES.search(text)
    if mc:
        res.set("chemo_cycles", mc.group(1), 0.7, "pattern", mc.group(0))


# --------------------------------------------------------------------------
def merge(existing: dict, new: ExtractionResult, overwrite: bool = False) -> dict:
    """
    يدمج استخراج جديد في بيانات موجودة.
    overwrite=False → لا يمسح القيم التي أدخلها المستخدم يدوياً.
    """
    out = dict(existing or {})
    for k, val in new.values.items():
        if overwrite or not out.get(k):
            out[k] = val
    return out

# -*- coding: utf-8 -*-
"""
محرك جودة البيانات — Data Quality Check
========================================
ثلاث عائلات من القواعد:

  A) الاكتمال  Completeness  — الحقول الإلزامية حسب معايير ENCR/IARC
  B) الصيغة    Validity      — ICD-O-3، ICD-10، TNM، الرقم الوطني، التواريخ
  C) المنطق    Consistency   — تسلسل التواريخ، الجنس مقابل الموقع، السلوك مقابل المرحلة

كل قاعدة تُعيد Issue:
    code      رقم القاعدة (مثال Q-A01) — يُستخدم في التقارير والمقارنة بين الدُفعات
    severity  error | warning | info
    field     الحقل المعني
    message   رسالة عربية واضحة للمستخدم
    fix       اقتراح الإصلاح

النتيجة النهائية: qc_score (0-100) و qc_status (pass/warning/error).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from datetime import date
from typing import Optional

from . import reference as ref
from .dictionary import FIELDS, REQUIRED_FIELDS, VITALITY_STATUS
from . import extractor
from .extractor import parse_date, iso

SEV_PENALTY = {"error": 12, "warning": 4, "info": 0}

# مواقع مزدوجة تستلزم تحديد الجانبية (ICD-O-3 laterality)
PAIRED_SITES = {
    "C40.0", "C40.1", "C40.2", "C40.3", "C40.9",   # عظام الأطراف
    "C44.2",                                        # الأذن الخارجية
    "C44.6", "C44.7",                               # أطراف
    "C50.0", "C50.1", "C50.2", "C50.3", "C50.4", "C50.5", "C50.6", "C50.8", "C50.9",  # ثدي
    "C56.9",                                        # مبيض
    "C62.0", "C62.9",                               # خصية
    "C64.9", "C65.9",                               # كلية / حوض كلية
    "C69.0", "C69.1", "C69.2", "C69.3", "C69.4", "C69.5", "C69.6", "C69.8", "C69.9",  # عين
    "C34.1", "C34.2", "C34.3", "C34.0", "C34.8", "C34.9",                             # رئة
    "C41.4",                                        # عظام الحوض
}

# مواقع حصرية لجنس معيّن
FEMALE_ONLY = re.compile(r"^C5[1-8]")       # C51-C58 الجهاز التناسلي الأنثوي
MALE_ONLY = re.compile(r"^(C60|C61|C62|C63)")

# مواقع يجب أن يكون فيها أساس التشخيص نسيجياً (6/7) للتبليغ عن الورم
TODAY = date.today()

MIN_AGE = 0
MAX_AGE = 120

# تغطية السجل: أي تشخيص قبل هذا التاريخ يُعتبر خارج النطاق
REGISTRY_COVERAGE_FROM = date(1995, 1, 1)


@dataclass
class Issue:
    code: str
    severity: str          # error | warning | info
    field: str
    message: str
    fix: str = ""

    def to_dict(self):
        return {"code": self.code, "severity": self.severity, "field": self.field,
                "field_label": (FIELDS.get(self.field) or {}).get("label_ar", self.field),
                "message": self.message, "fix": self.fix}

    def __str__(self):
        return f"[{self.severity.upper()}] {self.code} {self.message}"


@dataclass
class QCReport:
    issues: list = dc_field(default_factory=list)
    score: int = 100
    status: str = "not_run"
    checked_at: str = ""
    registry_no: str = ""

    # --- helpers ---
    def add(self, code, severity, fld, message, fix=""):
        self.issues.append(Issue(code, severity, fld, message, fix))

    @property
    def errors(self):
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self):
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def infos(self):
        return [i for i in self.issues if i.severity == "info"]

    def finalise(self):
        penalty = sum(SEV_PENALTY.get(i.severity, 0) for i in self.issues)
        self.score = max(0, 100 - penalty)
        if self.errors:
            self.status = "error"
        elif self.warnings:
            self.status = "warning"
        else:
            self.status = "pass"
        self.checked_at = date.today().isoformat()
        return self

    def to_dict(self):
        return {
            "score": self.score, "status": self.status,
            "errors": len(self.errors), "warnings": len(self.warnings),
            "infos": len(self.infos), "checked_at": self.checked_at,
            "issues": [i.to_dict() for i in self.issues],
        }

    def to_text(self, lang: str = "ar") -> str:
        order = {"error": 0, "warning": 1, "info": 2}
        lines = [f"نتيجة فحص الجودة: {self.score}/100 ({self.status})",
                 f"أخطاء: {len(self.errors)}  تحذيرات: {len(self.warnings)}  ملاحظات: {len(self.infos)}",
                 ""]
        for i in sorted(self.issues, key=lambda x: (order[x.severity], x.code)):
            icon = {"error": "✗", "warning": "⚠", "info": "ℹ"}[i.severity]
            lines.append(f"{icon} [{i.code}] {i.message}")
            if i.fix:
                lines.append(f"     → الإصلاح المقترح: {i.fix}")
        if not self.issues:
            lines.append("✓ لا توجد مشاكل — السجل مطابق للمعايير")
        return "\n".join(lines)


# ==========================================================================
#  فحص سجل واحد
# ==========================================================================
def check_case(record: dict, duplicates: Optional[set] = None) -> QCReport:
    """
    record: dict بالقيم الخام (نصوص/تواريخ) مفاتيحه أسماء الحقول في القاموس.
    duplicates: مجموعة مفاتيح (national_id|primary_site|diagnosis_date) موجودة مسبقاً.
    """
    r = QCReport(registry_no=str(record.get("registry_no", "")))
    g = lambda name: (record.get(name) or "")
    gs = lambda name: str(record.get(name) or "").strip()

    # ---------------------------------------------------------------- A. الاكتمال
    missing_required = []
    for name in REQUIRED_FIELDS:
        val = gs(name)
        if not val or val.lower() in ("none", "false", "null"):
            missing_required.append(name)
    if missing_required:
        labels = "، ".join((FIELDS[n]["label_ar"]) for n in missing_required)
        r.add("Q-A01", "error", missing_required[0],
              f"حقول إلزامية ناقصة: {labels}",
              "أكمل هذه الحقول — معايير ENCR/IARC تشترطها لقبول التبليغ")
    else:
        r.add("Q-A02", "info", "", "جميع الحقول الإلزامية مكتملة")

    # حقول موصى بها (غير إلزامية لكن غيابها يُضعف التحليل)
    recommended = ["grade", "basis_of_diagnosis", "summary_stage", "laterality",
                   "district", "medical_file_no", "vitality_status"]
    missing_rec = [n for n in recommended if not gs(n)]
    if missing_rec:
        r.add("Q-A03", "warning", missing_rec[0],
              "حقول موصى بها ناقصة: " +
              "، ".join(FIELDS[n]["label_ar"] for n in missing_rec),
              "هذه الحقول مطلوبة في تقارير CI5 والمقارنات الدولية")

    # ---------------------------------------------------------------- B. الصيغة
    # B01 الرقم الوطني
    nid = gs("national_id")
    if nid:
        digits = re.sub(r"\D", "", nid)
        if len(digits) != 12:
            r.add("Q-B01", "error", "national_id",
                  f"الرقم الوطني «{nid}» ليس 12 رقماً (عدد الأرقام: {len(digits)})",
                  "الرقم الوطني الليبي يتكون من 12 رقماً بالضبط")
        else:
            # أرقام متطابقة أو متسلسلة = غالباً إدخال خاطئ
            if len(set(digits)) <= 2:
                r.add("Q-B02", "warning", "national_id",
                      f"الرقم الوطني «{nid}» يبدو غير حقيقي (أرقام متكررة)",
                      "تحقق من المستند الأصلي")

    # B02 ICD-O-3 الموقع
    site = gs("primary_site")
    if site:
        norm = ref.normalise_site(site)
        if not re.match(r"^C\d{2}(\.\d{1,2})?$", norm):
            t = ref.topography()
            if not t:
                r.add("Q-B04", "warning", "primary_site",
                      "لم يُعثر على جدول ICD-O-3 للمواقع — تعذّر التحقق من الرمز",
                      "تأكد من وجود ملف refdata/icdo3_topography.csv")
            else:
                r.add("Q-B03", "error", "primary_site",
                      f"رمز ICD-O-3 «{site}» غير صالح — الصيغة الصحيحة C00.0 إلى C80.9",
                      "استخدم جدول ICD-O-3 Topography")
        elif not ref.is_valid_site(norm):
            r.add("Q-B03", "error", "primary_site",
                  f"رمز ICD-O-3 «{norm}» غير موجود في الجدول المرجعي",
                  "راجع جدول المواقع — قد يكون خطأ مطبعي")
        else:
            r.add("Q-B05", "info", "primary_site", f"الموقع صالح: {ref.site_label(norm)}")

    # B03 ICD-O-3 النسيج
    morph = gs("morphology")
    if morph:
        norm = ref.normalise_morphology(morph)
        if not re.match(r"^\d{4}/[0-369]$", norm):
            r.add("Q-B06", "error", "morphology",
                  f"رمز الفحص النسيجي «{morph}» غير صالح — الصيغة nnnn/b",
                  "مثال: 8070/3 (سرطانة حرشفية الخلايا)")
        elif not ref.is_valid_morphology(norm):
            r.add("Q-B07", "warning", "morphology",
                  f"رمز الفحص النسيجي «{norm}» غير موجود في الجدول المرجعي المضمّن",
                  "قد يكون رمزاً صحيحاً غير مُدرج في القائمة المختصرة — تحقق من ICD-O-3 الكامل")
        else:
            beh = ref.behaviour_from_morphology(norm)
            if beh != gs("behaviour") and gs("behaviour"):
                r.add("Q-B08", "error", "behaviour",
                      f"تعارض: رمز السلوك {gs('behaviour')} لا يطابق /{beh} في {norm}",
                      f"صحّح رمز السلوك إلى {beh} أو راجع رمز النسيج")

    # B04 ICD-10
    icd10 = gs("icd10_code")
    if icd10:
        if not re.match(r"^[CD]\d{2}(\.\d{1,2})?$", icd10):
            r.add("Q-B09", "error", "icd10_code",
                  f"رمز ICD-10 «{icd10}» غير صالح",
                  "الصيغة الصحيحة C00.0-C97 أو D00-D49")
        elif site:
            derived = ref.icd10_from_icdo3(site)
            if derived and derived != icd10:
                r.add("Q-B10", "warning", "icd10_code",
                      f"رمز ICD-10 «{icd10}» يختلف عن المتوقع من ICD-O-3 «{site}» ({derived})",
                      "تحقق — قد يكون الورم نقيلة (/6) في موقع مختلف عن الأولي")

    # B05 قيم القوائم
    for name in ("sex", "vitality_status", "basis_of_diagnosis", "laterality",
                 "grade", "behaviour", "summary_stage", "staging_system"):
        val = gs(name)
        if not val:
            continue
        opts = (FIELDS.get(name) or {}).get("options") or {}
        if opts and val not in opts:
            r.add("Q-B11", "error", name,
                  f"قيمة «{val}» غير موجودة ضمن الخيارات المعتمدة لـ{FIELDS[name]['label_ar']}",
                  "الخيارات: " + "، ".join(list(opts.keys())[:8]) + "…")

    # B06 قيم TNM
    for name in ("ct", "cn", "cm", "pt", "pn", "pm"):
        val = gs(name).upper()
        if not val:
            continue
        opts = (FIELDS.get(name) or {}).get("options") or {}
        if opts and val not in opts:
            r.add("Q-B12", "error", name,
                  f"قيمة TNM «{val}» غير صالحة في {FIELDS[name]['label_ar']}",
                  "استخدم قيماً من AJCC 8th: " + ", ".join(list(opts)[:6]) + " …")

    # B07 التواريخ
    date_fields = {
        "birth_date": "تاريخ الميلاد",
        "date_of_first_symptom": "تاريخ أول عرض",
        "date_of_diagnosis": "تاريخ التشخيص",
        "date_of_death": "تاريخ الوفاة",
        "last_followup_date": "آخر متابعة",
        "notification_date": "تاريخ التبليغ",
        "stage_date": "تاريخ التقسيم المرحلي",
        "recurrence_date": "تاريخ الانتكاسة",
    }
    parsed = {}
    for name, label in date_fields.items():
        raw = gs(name)
        if not raw:
            continue
        d = parse_date(raw)
        if not d:
            r.add("Q-B13", "error", name,
                  f"«{label}» ليس تاريخاً قابلاً للقراءة: {raw}",
                  "استخدم صيغة YYYY-MM-DD أو DD/MM/YYYY")
            continue
        if d > TODAY:
            r.add("Q-B14", "error", name,
                  f"«{label}» في المستقبل ({iso(d)}) — اليوم {iso(TODAY)}",
                  "تاريخ مستقبلي غير منطقي في سجل طبي")
        parsed[name] = d

    if parsed.get("date_of_diagnosis") and parsed["date_of_diagnosis"] < REGISTRY_COVERAGE_FROM:
        r.add("Q-B15", "warning", "date_of_diagnosis",
              f"تاريخ التشخيص {iso(parsed['date_of_diagnosis'])} قبل بداية تغطية السجل "
              f"({iso(REGISTRY_COVERAGE_FROM)})",
              "تحقق — قد تكون حالة قديمة أُدرجت بأثر رجعي")

    # ---------------------------------------------------------------- C. المنطق
    dob = parsed.get("birth_date")
    dod = parsed.get("date_of_diagnosis")
    ddt = parsed.get("date_of_death")
    lfu = parsed.get("last_followup_date")
    dfs = parsed.get("date_of_first_symptom")

    if dob and dob > TODAY:
        r.add("Q-C01", "error", "birth_date", "تاريخ الميلاد في المستقبل", "تحقق من الإدخال")

    if dob and dod and dob > dod:
        r.add("Q-C02", "error", "birth_date",
              f"تاريخ الميلاد ({iso(dob)}) بعد تاريخ التشخيص ({iso(dod)})",
              "صحّح أحد التاريخين — الميلاد يجب أن يسبق التشخيص")

    if dfs and dod and dfs > dod:
        r.add("Q-C03", "warning", "date_of_first_symptom",
              f"تاريخ أول عرض ({iso(dfs)}) بعد تاريخ التشخيص ({iso(dod)})",
              "عادةً تظهر الأعراض قبل التشخيص")

    if dod and ddt and dod > ddt:
        r.add("Q-C04", "error", "date_of_death",
              f"تاريخ الوفاة ({iso(ddt)}) قبل تاريخ التشخيص ({iso(dod)})",
              "الوفاة يجب أن تكون بعد التشخيص")

    if lfu and dod and lfu < dod:
        r.add("Q-C05", "warning", "last_followup_date",
              f"آخر متابعة ({iso(lfu)}) قبل تاريخ التشخيص ({iso(dod)})",
              "المتابعة تكون بعد التشخيص — تحقق من التواريخ")

    if ddt and lfu and lfu > ddt:
        r.add("Q-C06", "warning", "last_followup_date",
              f"آخر متابعة ({iso(lfu)}) بعد تاريخ الوفاة ({iso(ddt)})",
              "لا يمكن متابعة مريض بعد وفاته")

    # العمر
    age = record.get("age_at_diagnosis")
    if age not in (None, ""):
        try:
            age_i = int(float(age))
            if not (MIN_AGE <= age_i <= MAX_AGE):
                r.add("Q-C07", "error", "age_at_diagnosis",
                      f"العمر {age_i} خارج النطاق المنطقي (0-{MAX_AGE})", "تحقق من تاريخ الميلاد")
            if dob and dod:
                calc = dod.year - dob.year - ((dod.month, dod.day) < (dob.month, dob.day))
                if abs(calc - age_i) > 1:
                    r.add("Q-C08", "warning", "age_at_diagnosis",
                          f"العمر المُدخل ({age_i}) يختلف عن المحسوب من التواريخ ({calc})",
                          "اترك الحقل فارغاً ليُحسب تلقائياً")
        except (TypeError, ValueError):
            r.add("Q-C07", "error", "age_at_diagnosis", f"العمر «{age}» ليس رقماً", "أدخل رقماً صحيحاً")

    # حالة الحياة مقابل تاريخ الوفاة
    vs = gs("vitality_status")
    if vs.startswith("dead"):
        if not ddt:
            r.add("Q-C09", "error", "date_of_death",
                  "الحالة «متوفى» لكن تاريخ الوفاة فارغ", "أدخل تاريخ الوفاة من شهادة الوفاة أو السجل المدني")
        if not gs("cause_of_death") or gs("cause_of_death") == "na":
            r.add("Q-C10", "warning", "cause_of_death",
                  "الحالة «متوفى» لكن سبب الوفاة غير محدد", "حدد سبب الوفاة الأساسي (مطلوب لإحصاءات البقاء)")
    elif vs in ("alive",) and ddt:
        r.add("Q-C11", "error", "date_of_death",
              "الحالة «على قيد الحياة» لكن يوجد تاريخ وفاة", "صحّح حالة المريض أو احذف تاريخ الوفاة")

    if vs == "lost" and not lfu:
        r.add("Q-C12", "warning", "last_followup_date",
              "الحالة «مفقود المتابعة» بدون تاريخ آخر اتصال معروف",
              "سجّل آخر تاريخ حاولتم فيه التواصل")

    # الجنس مقابل الموقع
    sex = gs("sex")
    if site and sex:
        ns = ref.normalise_site(site)
        if MALE_ONLY.match(ns) and sex == "female":
            r.add("Q-C13", "error", "sex",
                  f"تناقض: الموقع {ns} ({ref.site_label(ns)}) خاص بالذكور لكن الجنس «أنثى»",
                  "تحقق من الجنس أو من رمز الموقع")
        elif FEMALE_ONLY.match(ns) and sex == "male":
            if ns.startswith("C50"):
                r.add("Q-C14", "warning", "sex",
                      f"سرطان ثدي لدى ذكر ({ns}) — نادر لكنه ممكن، تأكد من التوثيق",
                      "أرفق ما يثبت التشخيص")
            else:
                r.add("Q-C13", "error", "sex",
                      f"تناقض: الموقع {ns} ({ref.site_label(ns)}) خاص بالإناث لكن الجنس «ذكر»",
                      "تحقق من الجنس أو من رمز الموقع")

    # الجانبية
    if site:
        ns = ref.normalise_site(site)
        if ns in PAIRED_SITES and not gs("laterality"):
            r.add("Q-C15", "warning", "laterality",
                  f"الموقع {ns} مزدوج لكن الجانبية غير محددة",
                  "حدد: 1=أيمن، 2=أيسر، 4=ثنائي، 9=غير معروف")
        elif ns not in PAIRED_SITES and gs("laterality") in ("1", "2", "4"):
            r.add("Q-C16", "info", "laterality",
                  f"جانبية محددة ({gs('laterality')}) لموقع غير مزدوج ({ns})",
                  "استخدم 0 (لا ينطبق) لهذا الموقع")

    # السلوك مقابل المرحلة
    beh = gs("behaviour")
    mval = (gs("pm") or gs("cm") or "").upper()
    if beh == "2" and mval.startswith("M1"):
        r.add("Q-C17", "error", "behaviour",
              "ورم لابِد (/2) مع نقائل بعيدة (M1) — تناقض",
              "الورم اللابِد لا ينتقل؛ صحّح السلوك إلى /3 أو صحّح M")
    if gs("summary_stage") == "in_situ" and beh == "3":
        r.add("Q-C18", "warning", "summary_stage",
              "المرحلة الموجزة «لابِد» لكن السلوك /3 (خبيث غازي)", "راجع المرحلة الموجزة")
    if gs("summary_stage") == "localized" and mval.startswith("M1"):
        r.add("Q-C19", "error", "summary_stage",
              "المرحلة الموجزة «موضعي» مع M1 (نقائل بعيدة)", "المرحلة الموجزة يجب أن تكون «بعيد»")

    # اتساق TNM مع المرحلة
    t = (gs("pt") or gs("ct") or "").upper()
    n = (gs("pn") or gs("cn") or "").upper()
    m = mval
    expected_stage = ref.derive_stage_group(gs("primary_site"), t, n, m) if (t or n or m) else ""
    for stage_field in ("pathological_stage", "clinical_stage"):
        entered = gs(stage_field)
        if entered and expected_stage and entered != expected_stage:
            r.add("Q-C20", "warning", stage_field,
                  f"المرحلة المُدخلة «{entered}» تختلف عن المستنتجة من TNM ({t}{n}{m}) = «{expected_stage}»",
                  "تحقق من نظام التقسيم المستخدم أو من قيم TNM")

    # M1 يقتضى summary_stage = distant
    if m.startswith("M1") and gs("summary_stage") not in ("distant", ""):
        r.add("Q-C21", "error", "summary_stage",
              f"يوجد M1 لكن المرحلة الموجزة «{gs('summary_stage')}»", "يجب أن تكون «بعيد / distant»")
    if m.startswith("M1") and not gs("summary_stage"):
        r.add("Q-C21", "warning", "summary_stage", "يوجد M1 لكن المرحلة الموجزة فارغة", "حدد «بعيد»")

    # flags العلاج مقابل الملخص
    summary_raw = gs("treatment_summary")
    summary = summary_raw.lower()

    def _mentioned(keys):
        """هل ذُكر العلاج فعلاً (وليس منفياً: «Surgery: NOT performed»)؟"""
        for k in keys:
            for m in re.finditer(re.escape(k.lower()), summary):
                window = summary_raw[max(0, m.start() - 12):m.end() + 34]
                if not extractor.NEGATION.search(window):
                    return True
        return False
    flag_map = {
        "surgery_performed": (["جراح", "surgery", "استئصال", "resection", "mastectomy"], "جراحة"),
        "chemotherapy_given": (["كيميائي", "كيماوي", "chemo", "adriamycin", "cisplatin"], "علاج كيميائي"),
        "radiotherapy_given": (["إشعاع", "اشعاع", "radio", "radiation", "gy"], "علاج إشعاعي"),
        "hormonal_given": (["هرمون", "hormon", "tamoxifen", "letrozole"], "علاج هرموني"),
        "immunotherapy_given": (["مناعي", "immuno", "موجه", "targeted", "trastuzumab"], "علاج مناعي/موجّه"),
    }
    for fname, (keys, arlabel) in flag_map.items():
        flag = str(record.get(fname, "")).lower() in ("true", "1", "yes", "نعم")
        mentioned = _mentioned(keys)
        if flag and not mentioned and summary:
            r.add("Q-C22", "info", fname,
                  f"علم «{arlabel}» مفعّل لكنه غير مذكور في ملخص العلاج", "أضف التفاصيل إلى الملخص")
        if mentioned and not flag:
            r.add("Q-C23", "warning", fname,
                  f"ملخص العلاج يذكر {arlabel} لكن العلم غير مفعّل", f"فعّل حقل «{FIELDS.get(fname, {}).get('label_ar', fname)}»")

    # first course within 4 months
    if str(record.get("first_course_within_4m", "")).lower() in ("true", "1", "yes") \
            and not any(_mentioned(flag_map[k][0]) or str(record.get(k, "")).lower() in ("true", "1")
                        for k in flag_map):
        r.add("Q-C24", "warning", "first_course_within_4m",
              "مؤشر «العلاج الأول خلال 4 أشهر» مفعّل بدون أي علاج مسجّل",
              "سجّل العلاج أو أوقف المؤشر")

    # مدة البقاء
    surv = record.get("survival_months")
    if surv not in (None, ""):
        try:
            si = int(float(surv))
            if si < 0:
                r.add("Q-C25", "error", "survival_months", "مدة البقاء سالبة", "تحقق من التواريخ")
            elif dod and ddt and si > (ddt - dod).days / 30.44 + 1:
                r.add("Q-C26", "warning", "survival_months",
                      f"مدة البقاء ({si} شهراً) أطول من الفرق بين التشخيص والوفاة",
                      "اتركها لتُحسب تلقائياً")
        except (TypeError, ValueError):
            r.add("Q-C25", "error", "survival_months", f"«{surv}» ليس رقماً", "أدخل عدداً صحيحاً بالأشهر")

    # ---------------------------------------------------------------- التكرار
    if dod:
        key = f"{nid}|{ref.normalise_site(site)}|{iso(dod)}"
        if duplicates is not None and key in duplicates:
            r.add("Q-D01", "error", "national_id",
                  "يوجد سجل مطابق (نفس الرقم الوطني + نفس الموقع + نفس تاريخ التشخيص)",
                  "راجع قائمة السجلات — قد يكون تبليغاً مكرراً لنفس الورم")

    # تعدد الأورام
    pc = record.get("primary_count")
    if pc:
        try:
            if int(pc) > 1 and not str(record.get("multiple_primaries", "")).lower() in ("true", "1", "yes"):
                r.add("Q-D02", "warning", "multiple_primaries",
                      f"عدد الأورام الأولية {pc} لكن مؤشر «أورام متعددة» غير مفعّل", "فعّل المؤشر")
        except (TypeError, ValueError):
            pass

    # ---------------------------------------------------------------- الاسم
    if str(record.get("_name_split_auto", "")).lower() in ("true", "1", "yes"):
        r.add("Q-F01", "warning", "first_name",
              "تم تقسيم الاسم إلى (أول/أب/جد/عائلة) آلياً من الاسم الكامل",
              "قارن الأجزاء بالمستند الأصلي — التقسيم الآلي للاسم العربي قد يخطئ")
    if gs("full_name"):
        words = len(gs("full_name").split())
        if words < 2:
            r.add("Q-F02", "warning", "full_name",
                  f"الاسم «{gs('full_name')}» كلمة واحدة — السجل الليبي يستلزم اسماً ثلاثياً على الأقل",
                  "أكمل الاسم من البطاقة الشخصية أو الملف الطبي")

    # ---------------------------------------------------------------- المستندات
    docs = record.get("document_count") or 0
    try:
        if int(docs) == 0:
            r.add("Q-E01", "warning", "document_ids",
                  "لا يوجد مستند أصلي مرفق بالسجل",
                  "ارفع التقرير الممسوح ضوئياً — مطلوب للأرشفة والتدقيق")
    except (TypeError, ValueError):
        pass

    conf = record.get("extraction_confidence")
    if conf not in (None, ""):
        try:
            if float(conf) < 60:
                r.add("Q-E02", "warning", "extraction_confidence",
                      f"ثقة الاستخراج الآلي منخفضة ({conf}%)", "راجع كل الحقول يدوياً مقابل المستند الأصلي")
        except (TypeError, ValueError):
            pass

    return r.finalise()


# ==========================================================================
#  فحص دُفعة (Batch)
# ==========================================================================
def check_batch(records: list) -> dict:
    """
    يفحص قائمة سجلات ويعيد إحصاءات الدفعة + كشف التكرار.
    يُستخدم في واجهة «فحص الجودة لكل الملفات».
    """
    seen, dupes = {}, set()
    for rec in records:
        dod = parse_date(rec.get("date_of_diagnosis"))
        parts = [str(rec.get("national_id") or ""),
                 ref.normalise_site(str(rec.get("primary_site") or "")),
                 iso(dod) if dod else ""]
        if all(parts):
            key = "|".join(parts)          # مفتاح نصى — Excel لا يقبل الـ tuple
            seen.setdefault(key, []).append(rec.get("registry_no", "?"))
            if len(seen[key]) > 1:
                dupes.add(key)

    reports = []
    for rec in records:
        reports.append((rec, check_case(rec, duplicates=dupes)))

    total = len(reports)
    by_status = {"pass": 0, "warning": 0, "error": 0}
    all_issues = []
    for rec, rep in reports:
        by_status[rep.status] = by_status.get(rep.status, 0) + 1
        for iss in rep.issues:
            if iss.severity in ("error", "warning"):
                all_issues.append({"registry_no": rec.get("registry_no", ""),
                                   "name": rec.get("full_name", ""),
                                   **iss.to_dict()})

    # أكثر المشاكل تكراراً
    freq = {}
    for i in all_issues:
        freq[i["code"]] = freq.get(i["code"], 0) + 1
    top_issues = sorted(freq.items(), key=lambda x: -x[1])[:15]

    avg_score = round(sum(rep.score for _, rep in reports) / total, 1) if total else 0
    return {
        "total": total,
        "by_status": by_status,
        "avg_score": avg_score,
        "duplicates": [{"key": k, "records": v} for k, v in seen.items() if len(v) > 1],
        "top_issues": top_issues,
        "issues": all_issues,
        "reports": reports,
    }


# ==========================================================================
#  قاعدة المعرفة: شرح كل رمز قاعدة
# ==========================================================================
RULE_CATALOGUE = {
    "Q-A01": ("الاكتمال", "حقول إلزامية ناقصة", "error", "ENCR/IARC — الحد الأدنى المقبول للتبليغ"),
    "Q-A02": ("الاكتمال", "الحقول الإلزامية مكتملة", "info", "—"),
    "Q-A03": ("الاكتمال", "حقول موصى بها ناقصة", "warning", "CI5 Vol. XI — مطلوبة للمقارنات الدولية"),
    "Q-B01": ("الصيغة", "الرقم الوطني ليس 12 رقماً", "error", "المنظومة الوطنية الليبية"),
    "Q-B02": ("الصيغة", "الرقم الوطني يبدو غير حقيقي", "warning", "كشف أخطاء الإدخال"),
    "Q-B03": ("الصيغة", "رمز ICD-O-3 للموقع غير صالح", "error", "ICD-O-3 Topography"),
    "Q-B04": ("الصيغة", "الجدول المرجعي غير متوفر", "warning", "—"),
    "Q-B05": ("الصيغة", "رمز الموقع صالح", "info", "ICD-O-3"),
    "Q-B06": ("الصيغة", "رمز الفحص النسيجي غير صالح", "error", "ICD-O-3 Morphology"),
    "Q-B07": ("الصيغة", "رمز الفحص النسيجي غير مدرج", "warning", "ICD-O-3"),
    "Q-B08": ("الصيغة", "تعارض بين رمز السلوك ورمز النسيج", "error", "ICD-O-3 field 5"),
    "Q-B09": ("الصيغة", "رمز ICD-10 غير صالح", "error", "ICD-10 Chapter II"),
    "Q-B10": ("الصيغة", "ICD-10 لا يطابق ICD-O-3", "warning", "ICD-10 / ICD-O-3 cross-walk"),
    "Q-B11": ("الصيغة", "قيمة خارج القوائم المعتمدة", "error", "قاموس الحقول"),
    "Q-B12": ("الصيغة", "قيمة TNM غير صالحة", "error", "AJCC 8th / UICC"),
    "Q-B13": ("الصيغة", "تاريخ غير قابل للقراءة", "error", "ISO 8601"),
    "Q-B14": ("الصيغة", "تاريخ في المستقبل", "error", "منطق السجلات الطبية"),
    "Q-B15": ("الصيغة", "تشخيص قبل بداية تغطية السجل", "warning", "سجل السرطان — التغطية الزمنية"),
    "Q-C01": ("المنطق", "تاريخ الميلاد في المستقبل", "error", "—"),
    "Q-C02": ("المنطق", "الميلاد بعد التشخيص", "error", "تسلسل زمني"),
    "Q-C03": ("المنطق", "الأعراض بعد التشخيص", "warning", "تسلسل زمني"),
    "Q-C04": ("المنطق", "الوفاة قبل التشخيص", "error", "تسلسل زمني"),
    "Q-C05": ("المنطق", "المتابعة قبل التشخيص", "warning", "تسلسل زمني"),
    "Q-C06": ("المنطق", "متابعة بعد الوفاة", "warning", "تسلسل زمني"),
    "Q-C07": ("المنطق", "العمر خارج النطاق", "error", "0-120 سنة"),
    "Q-C08": ("المنطق", "العمر لا يطابق التواريخ", "warning", "اتساق داخلي"),
    "Q-C09": ("المنطق", "متوفى بدون تاريخ وفاة", "error", "إحصاءات البقاء"),
    "Q-C10": ("المنطق", "متوفى بدون سبب وفاة", "warning", "ICD-10 cause of death"),
    "Q-C11": ("المنطق", "حي مع تاريخ وفاة", "error", "اتساق داخلي"),
    "Q-C12": ("المنطق", "مفقود المتابعة بدون تاريخ اتصال", "warning", "متابعة نشطة"),
    "Q-C13": ("المنطق", "الجنس لا يتوافق مع الموقع", "error", "ICD-O-3 topography × sex"),
    "Q-C14": ("المنطق", "سرطان ثدي لدى ذكر", "warning", "حالة نادرة تستوجب توثيقاً"),
    "Q-C15": ("المنطق", "موقع مزدوج بدون جانبية", "warning", "ICD-O-3 field 5 laterality"),
    "Q-C16": ("المنطق", "جانبية لموقع غير مزدوج", "info", "ICD-O-3"),
    "Q-C17": ("المنطق", "ورم لابِد مع نقائل", "error", "ICD-O-3 behaviour × TNM"),
    "Q-C18": ("المنطق", "مرحلة موجزة لابِد مع سلوك /3", "warning", "SEER × ICD-O-3"),
    "Q-C19": ("المنطق", "مرحلة موضعية مع M1", "error", "SEER Summary Stage"),
    "Q-C20": ("المنطق", "المرحلة لا تطابق TNM", "warning", "AJCC 8th stage grouping"),
    "Q-C21": ("المنطق", "M1 بدون مرحلة موجزة «بعيد»", "error", "SEER Summary Stage"),
    "Q-C22": ("المنطق", "علم علاج مفعّل غير مذكور في الملخص", "info", "اتساق داخلي"),
    "Q-C23": ("المنطق", "ملخص يذكر علاجاً والعلم غير مفعّل", "warning", "اتساق داخلي"),
    "Q-C24": ("المنطق", "مؤشر 4 أشهر بدون علاج مسجّل", "warning", "SEER RXSUMM-1st course"),
    "Q-C25": ("المنطق", "مدة البقاء غير صالحة", "error", "حساب البقاء"),
    "Q-C26": ("المنطق", "مدة البقاء أطول من الفترة", "warning", "حساب البقاء"),
    "Q-D01": ("التكرار", "سجل مكرر", "error", "كشف التكرار (national_id + site + date)"),
    "Q-D02": ("التكرار", "تعدد أورام بدون مؤشر", "warning", "IARC multiple primary rules"),
    "Q-E01": ("التوثيق", "لا يوجد مستند مرفق", "warning", "الأرشفة والتدقيق"),
    "Q-E02": ("التوثيق", "ثقة الاستخراج منخفضة", "warning", "مراجعة يدوية إلزامية"),
    "Q-F01": ("الاسم", "تقسيم آلي للاسم يحتاج تأكيداً", "warning", "قواعد التسمية العربية"),
    "Q-F02": ("الاسم", "الاسم أقل من ثلاثي", "warning", "متطلبات السجل المدني الليبي"),
}


if __name__ == "__main__":
    demo = {
        "registry_no": "CR2026/0001", "national_id": "119850123456",
        "first_name": "فاطمة", "father_name": "علي", "family_name": "العمروني",
        "sex": "female", "birth_date": "1971-03-14", "date_of_diagnosis": "2024-06-02",
        "primary_site": "C50.4", "morphology": "8500/3", "district": "zawiya",
        "reporting_facility": "المعهد القومي للأورام - صبراتة",
        "vitality_status": "alive", "basis_of_diagnosis": "6",
        "ct": "T2", "cn": "N1", "cm": "M0", "document_count": 1,
    }
    rep = check_case(demo)
    print(rep.to_text())
    print("\nScore:", rep.score, rep.status)

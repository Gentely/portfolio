# -*- coding: utf-8 -*-
"""
قاموس حقول سجل السرطان — Cancer Registry Data Dictionary
=========================================================
المصدر الوحيد للحقيقة (Single Source of Truth).

يُستخدم في ثلاثة أماكن:
  1) الأداة المستقلة (webapp/cli)  -> بناء النماذج والتحقق والتصدير.
  2) وحدة أودو                       -> يولّد منها الحقول وقوائم الاختيار.
  3) محرك جودة البيانات              -> قواعد الإلزام والتحقق.

المعايير المرجعية:
  - ICD-O-3        (International Classification of Diseases for Oncology, 3rd ed.)
  - ICD-10         (Chapter II: Neoplasms C00-D49)
  - AJCC 8th ed. / UICC TNM
  - IARC / ENCR     (European Network of Cancer Registries) — البيانات الإلزامية
  - CI5 Vol. XI     (Cancer Incidence in Five Continents)
"""

from collections import OrderedDict

# --------------------------------------------------------------------------
# 0) القوائم المرجعية (Selection lists)
# --------------------------------------------------------------------------

SEX = OrderedDict([
    ("male",   ("ذكر", "Male")),
    ("female", ("أنثى", "Female")),
    ("unknown",("غير معروف", "Unknown")),
])

VITALITY_STATUS = OrderedDict([
    ("alive",            ("على قيد الحياة", "Alive")),
    ("dead",             ("متوفى", "Deceased")),
    ("dead_cancer",      ("متوفى بسبب الورم", "Deceased - cancer cause")),
    ("dead_other",       ("متوفى بسبب آخر", "Deceased - other cause")),
    ("dead_unknown",     ("متوفى - سبب غير معروف", "Deceased - unknown cause")),
    ("lost",             ("مفقود المتابعة", "Lost to follow-up")),
    ("emigrated",        ("مهاجر خارج البلاد", "Emigrated")),
    ("unknown",          ("غير معروف", "Unknown")),
])

# ICD-O-3 Field 10 — Basis of Diagnosis
BASIS_OF_DIAGNOSIS = OrderedDict([
    ("0", ("0 - تشريح بعد الوفاة فقط", "Autopsy, death certificate only")),
    ("1", ("1 - سريري فقط", "Clinical investigation only")),
    ("2", ("2 - تنظير / تصوير", "Endoscopy / Radiology / Imaging")),
    ("3", ("3 - جراحة استكشافية / خزعة جراحية", "Surgical exploration / biopsy")),
    ("4", ("4 - تشريح مجهري لنقيلة", "Cytology / Histology of metastasis")),
    ("5", ("5 - تشريح مجهري لخلايا (سيتولوجيا)", "Cytology of primary (incl. endoscopy)")),
    ("6", ("6 - تشريح مجهري للورم الأولي", "Histology of primary tumour")),
    ("7", ("7 - تشريح مجهري قبل الوفاة", "Histology before death")),
    ("9", ("9 - طريقة غير معروفة", "Unknown basis")),
])

# ICD-O-3 Field 5 — Laterality
LATERALITY = OrderedDict([
    ("0", ("0 - لا ينطبق (ليس موقعاً مزدوجاً)", "Not a paired site")),
    ("1", ("1 - أيمن", "Right")),
    ("2", ("2 - أيسر", "Left")),
    ("3", ("3 - جانب واحد فقط غير محدد", "One side only, NOS")),
    ("4", ("4 - ثنائي الجانب", "Bilateral")),
    ("5", ("5 - خط الوسط", "Midline")),
    ("9", ("9 - غير معروف", "Unknown / not stated")),
])

# ICD-O-3 Field 6 — Histological Grade / Differentiation
GRADE = OrderedDict([
    ("1", ("G1 - جيد التمايز", "Well differentiated")),
    ("2", ("G2 - متوسط التمايز", "Moderately differentiated")),
    ("3", ("G3 - ضعيف التمايز", "Poorly differentiated")),
    ("4", ("G4 - غير متمايز", "Undifferentiated / anaplastic")),
    ("5", ("T5 - خلايا تائية (لمفومات)", "T-cell")),
    ("6", ("B6 - خلايا بائية (لمفومات)", "B-cell")),
    ("7", ("07 - صفر (لمفومات)", "Null cell")),
    ("8", ("08 - صفر (لمفومات)", "NK cell")),
    ("9", ("G9 - درجة غير محددة", "Grade not determined / not applicable")),
])

BEHAVIOUR = OrderedDict([
    ("0", ("/0 - حميد", "Benign")),
    ("1", ("/1 - سلوك غير مؤكد", "Uncertain whether benign or malignant")),
    ("2", ("/2 - لابِد (in situ)", "Carcinoma in situ / non-invasive")),
    ("3", ("/3 - خبيث، موقع أولي", "Malignant, primary site")),
    ("6", ("/6 - خبيث، موقع ثانوي (نقيلة)", "Malignant, metastatic site")),
    ("9", ("/9 - خبيث، أولي أو ثانوي غير مؤكد", "Malignant, uncertain primary or metastatic")),
])

STAGING_SYSTEM = OrderedDict([
    ("ajcc8",    ("AJCC الإصدار الثامن (2017)", "AJCC 8th Edition")),
    ("ajcc7",    ("AJCC الإصدار السابع (2010)", "AJCC 7th Edition")),
    ("uicc8",    ("UICC الإصدار الثامن", "UICC 8th Edition")),
    ("seer",     ("SEER Summary Stage", "SEER Summary Stage")),
    ("figo",     ("FIGO (أورام نسائية)", "FIGO (gynaecological)")),
    ("ann_arbor",("Ann Arbor (لمفومات)", "Ann Arbor (lymphoma)")),
    ("dukes",    ("Dukes (قولون)", "Dukes (colon)")),
    ("other",    ("نظام آخر", "Other")),
    ("none",     ("لا يوجد تقسيم مرحلي", "Not applicable / not staged")),
])

SUMMARY_STAGE = OrderedDict([
    ("in_situ",   ("لابِد (In situ)", "In situ")),
    ("localized", ("موضعي (Localized)", "Localized")),
    ("regional",  ("إقليمي (Regional)", "Regional")),
    ("distant",   ("بعيد / منتقل (Distant)", "Distant")),
    ("unknown",   ("غير معروف", "Unknown")),
])

T_STAGE = OrderedDict([(v, (v, v)) for v in
    ["TX", "T0", "Tis", "T1", "T1a", "T1b", "T1c", "T1mi",
     "T2", "T2a", "T2b", "T2c", "T3", "T3a", "T3b", "T3c", "T3d",
     "T4", "T4a", "T4b", "T4c", "T4d", "T4e"]])

N_STAGE = OrderedDict([(v, (v, v)) for v in
    ["NX", "N0", "N0(i+)", "N0(mol+)", "N1", "N1a", "N1b", "N1c", "N1mi",
     "N2", "N2a", "N2b", "N2c", "N3", "N3a", "N3b", "N3c"]])

M_STAGE = OrderedDict([(v, (v, v)) for v in
    ["MX", "M0", "M1", "M1a", "M1b", "M1c", "M1d"]])

STAGE_GROUP = OrderedDict([(v, (v, v)) for v in
    ["Occult", "Stage 0", "Stage I", "Stage IA", "Stage IA1", "Stage IA2", "Stage IA3",
     "Stage IB", "Stage IB1", "Stage IB2", "Stage IB3", "Stage IC",
     "Stage II", "Stage IIA", "Stage IIA1", "Stage IIA2", "Stage IIB", "Stage IIC",
     "Stage III", "Stage IIIA", "Stage IIIA1", "Stage IIIA2", "Stage IIIB", "Stage IIIC",
     "Stage IIIC1", "Stage IIIC2", "Stage IIID",
     "Stage IV", "Stage IVA", "Stage IVB", "Stage IVC",
     "Unknown"]])

TREATMENT_MODALITY = OrderedDict([
    ("surgery",      ("جراحة (استئصال الورم)", "Surgery / Tumour resection")),
    ("biopsy_only",  ("خزعة تشخيصية فقط", "Biopsy / diagnostic only")),
    ("chemotherapy", ("علاج كيميائي", "Chemotherapy")),
    ("radiotherapy", ("علاج إشعاعي", "Radiotherapy")),
    ("chemorad",     ("علاج كيميائي-إشعاعي متزامن", "Concurrent chemoradiation")),
    ("immunotherapy",("علاج مناعي", "Immunotherapy")),
    ("targeted",     ("علاج موجّه (مستهدف)", "Targeted therapy")),
    ("hormonal",     ("علاج هرموني", "Hormonal / Endocrine therapy")),
    ("bmt",          ("زرع نقي العظم / خلايا جذعية", "Bone marrow / Stem cell transplant")),
    ("ablation",     ("كيّ / استئصال موضعي", "Ablation (RFA, cryo, TACE)")),
    ("palliative",   ("علاج تلطيفي", "Palliative care")),
    ("none",         ("لم يتلقَّ علاجاً", "No treatment given")),
    ("refused",      ("رفض العلاج", "Treatment refused")),
    ("other",        ("علاج آخر", "Other / NOS")),
    ("unknown",      ("غير معروف", "Unknown")),
])

RADIOTHERAPY_TYPE = OrderedDict([
    ("external", ("إشعاع خارجي (EBRT)", "External beam")),
    ("brachy",   ("علاج قريب (Brachytherapy)", "Brachytherapy")),
    ("sbrt",     ("علاج إشعاعي مجسّم (SBRT/SRS)", "Stereotactic body / radiosurgery")),
    ("radioiso", ("نظائر مشعة جهازية", "Systemic radioisotope")),
    ("other",    ("أخرى", "Other")),
    ("unknown",  ("غير معروف", "Unknown")),
])

TREATMENT_RESPONSE = OrderedDict([
    ("cr",   ("استجابة كاملة (CR)", "Complete response")),
    ("pr",   ("استجابة جزئية (PR)", "Partial response")),
    ("sd",   ("مرض مستقر (SD)", "Stable disease")),
    ("pd",   ("تطور المرض (PD)", "Progressive disease")),
    ("na",   ("غير قابل للتقييم", "Not assessable")),
    ("unk",  ("غير معروف", "Unknown")),
])

DISEASE_STATUS_LAST = OrderedDict([
    ("ned",      ("خالٍ من المرض (NED)", "No evidence of disease")),
    ("awd",      ("مصاب بالمرض (AWD)", "Alive with disease")),
    ("stable",   ("مستقر", "Stable")),
    ("progress", ("متقدم", "Progressive")),
    ("relapse",  ("انتكاسة", "Relapsed")),
    ("metastatic",("منتشر", "Metastatic")),
    ("unknown",  ("غير معروف", "Unknown")),
])

DATA_ENTRY_STATUS = OrderedDict([
    ("draft",     ("مسودة", "Draft")),
    ("scanned",   ("تم المسح الضوئي", "Scanned")),
    ("extracted", ("تم الاستخراج الآلي", "Auto-extracted")),
    ("review",    ("قيد المراجعة", "Under review")),
    ("validated", ("معتمد", "Validated")),
    ("qc_failed", ("فشل فحص الجودة", "Failed QC")),
    ("exported",  ("تم التصدير", "Exported")),
])

QC_STATUS = OrderedDict([
    ("not_run", ("لم يُجرَ الفحص", "Not checked")),
    ("pass",    ("ناجح", "Pass")),
    ("warning", ("تحذير", "Warning")),
    ("error",   ("خطأ", "Error")),
])

# بلديات ليبيا الـ 22 (للتقارير الجغرافية)
LIBYA_DISTRICTS = OrderedDict([
    ("butnan",       ("البطنان", "Butnan")),
    ("derna",        ("درنة", "Derna")),
    ("jabal_akhdar", ("الجبل الأخضر", "Jabal al Akhdar")),
    ("marj",         ("المرج", "Marj")),
    ("benghazi",     ("بنغازي", "Benghazi")),
    ("al_wahat",     ("الواحات", "Al Wahat")),
    ("al_kufrah",    ("الكفرة", "Al Kufrah")),
    ("sirte",        ("سرت", "Sirte")),
    ("misrata",      ("مصراتة", "Misrata")),
    ("murqub",       ("المرقب", "Murqub")),
    ("tripoli",      ("طرابلس", "Tripoli")),
    ("jafara",       ("الجفارة", "Jafara")),
    ("zawiya",       ("الزاوية", "Zawiya")),
    ("nuqat_khams",  ("النقاط الخمس", "Nuqat al Khams")),
    ("jabal_gharbi", ("الجبل الغربي", "Jabal al Gharbi")),
    ("nalut",        ("نالوت", "Nalut")),
    ("ghat",         ("غات", "Ghat")),
    ("wadi_hayaa",   ("وادي الحياة", "Wadi al Hayaa")),
    ("sabha",        ("سبها", "Sabha")),
    ("wadi_shatii",  ("وادي الشاطئ", "Wadi al Shatii")),
    ("murzuq",       ("مرزق", "Murzuq")),
    ("jufra",        ("الجفرة", "Jufra")),
])

# مراكز العلاج المرجعية في ليبيا
TREATMENT_CENTRES = OrderedDict([
    ("nci_sabratha", ("المعهد القومي للأورام - صبراتة", "NCI Sabratha")),
    ("nci_benghazi", ("المعهد القومي للأورام - بنغازي", "NCI Benghazi")),
    ("tripoli_medical", ("مركز طرابلس الطبي", "Tripoli Medical Centre")),
    ("misrata_oncology", ("مركز مصراتة للأورام", "Misrata Oncology Centre")),
    ("sabha_medical", ("مركز سبها الطبي", "Sabha Medical Centre")),
    ("private", ("مركز خاص", "Private facility")),
    ("abroad", ("خارج البلاد", "Treated abroad")),
    ("other", ("أخرى", "Other")),
    ("unknown", ("غير معروف", "Unknown")),
])

# قيمة «لا ينطبق» الصحيحة لكل قائمة — مهمة لأورام الدم التي لا يُطبَّق عليها TNM
NOT_APPLICABLE_MAP = {
    "summary_stage": "unknown",
    "staging_system": "none",
    "laterality": "0",
    "grade": "9",
    "basis_of_diagnosis": "9",
    "vitality_status": "unknown",
    "cause_of_death": "na",
    "treatment_response": "na",
    "last_disease_status": "unknown",
    "radiotherapy_type": "unknown",
    "clinical_stage": "Unknown",
    "pathological_stage": "Unknown",
}

NOT_APPLICABLE_RE = (r"^(?:not\s+applicable|n/?a|nil|none|لا\s*ينطبق|غير\s*منطبق|"
                     r"غير\s*قابل\s*للتطبيق|لا\s*يوجد|\-)(?:[\s\-–—:,;.]|$)")

# أسباب الوفاة المبسّطة (تُطابق مع ICD-10 عند الحاجة)
CAUSE_OF_DEATH = OrderedDict([
    ("cancer",     ("الورم الخبيث نفسه", "The malignancy itself")),
    ("cancer_tx",  ("مضاعفات العلاج", "Treatment complication")),
    ("infection",  ("إنتان", "Infection / sepsis")),
    ("other_disease", ("مرض آخر", "Other disease")),
    ("accident",   ("حادث / سبب خارجي", "Accident / external cause")),
    ("unknown",    ("غير معروف", "Unknown")),
    ("na",         ("لا ينطبق - على قيد الحياة", "Not applicable")),
])


# --------------------------------------------------------------------------
# 1) قاموس الحقول
#    كل حقل: name, ar, en, type, group, required, options, help, validation
# --------------------------------------------------------------------------

F = lambda name, ar, en, type, group, **kw: dict(
    name=name, label_ar=ar, label_en=en, type=type, group=group,
    required=kw.get("required", False),
    options=kw.get("options"),
    ref=kw.get("ref", ""),
    help_ar=kw.get("help", ""),
    max_len=kw.get("max_len", 128),
    pattern=kw.get("pattern", ""),
    export=kw.get("export", True),
    export_width=kw.get("width", 18),
)

DATA_DICTIONARY = [
    # ---------------- A. معرّفات السجل ----------------
    F("registry_no", "رقم السجل في المكتب", "Registry accession no.", "char", "A. Identifiers",
      required=True, pattern=r"^CR\d{4,}(/\d{2,4})?$",
      help="يُولَّد تلقائياً بصيغة CR2026/0001", width=16),
    F("national_id", "الرقم الوطني", "National ID number", "char", "A. Identifiers",
      required=True, pattern=r"^\d{12}$",
      help="12 رقماً — يُستخدم لمنع التكرار بين السجلات", width=18),
    F("medical_file_no", "رقم الملف الطبي", "Hospital medical record no.", "char", "A. Identifiers",
      help="رقم الملف في المستشفى المبلِّغ", width=18),
    F("reporting_facility", "الجهة المبلِّغة", "Reporting facility", "char", "A. Identifiers",
      required=True, help="اسم المستشفى/المركز الذي ورد منه التبليغ", width=28),
    F("reporter_name", "اسم المبلِّغ", "Notifier / reporter", "char", "A. Identifiers",
      width=24),
    F("notification_date", "تاريخ التبليغ", "Date of notification", "date", "A. Identifiers",
      width=14),

    # ---------------- B. البيانات الديموغرافية ----------------
    F("first_name", "الاسم الأول", "First name", "char", "B. Demographics",
      required=True, width=20),
    F("father_name", "اسم الأب", "Father's name", "char", "B. Demographics",
      required=True, width=20),
    F("grandfather_name", "اسم الجد", "Grandfather's name", "char", "B. Demographics",
      width=20),
    F("family_name", "اسم العائلة / اللقب", "Family name", "char", "B. Demographics",
      required=True, width=22),
    F("full_name", "الاسم الكامل", "Full name", "char", "B. Demographics",
      help="يُحسب تلقائياً من الرباعي — قابل للتعديل", width=40),
    F("sex", "الجنس", "Sex", "selection", "B. Demographics",
      required=True, options=SEX, width=10),
    F("birth_date", "تاريخ الميلاد", "Date of birth", "date", "B. Demographics",
      required=True, help="إن كان مجهولاً يُستخدم 01-01 من السنة", width=14),
    F("birth_date_known", "تاريخ الميلاد معروف بدقة", "Exact DOB known", "boolean",
      "B. Demographics", help="إن كان غير معروف → السنة التقديرية فقط", width=14),
    F("age_at_diagnosis", "العمر عند التشخيص", "Age at diagnosis (years)", "integer",
      "B. Demographics", help="يُحسب تلقائياً = تاريخ التشخيص − تاريخ الميلاد", width=14),
    F("district", "البلدية", "District (Baladiya)", "selection", "B. Demographics",
      options=LIBYA_DISTRICTS, required=True, width=18),
    F("city", "المدينة / المحلة", "City / locality", "char", "B. Demographics", width=18),
    F("address", "العنوان التفصيلي", "Full address", "text", "B. Demographics",
      max_len=300, width=32),
    F("phone", "رقم الهاتف", "Phone number", "char", "B. Demographics",
      pattern=r"^[0-9+\-\s]{7,20}$", width=16),

    # ---------------- C. التشخيص والورم ----------------
    F("date_of_diagnosis", "تاريخ أول تشخيص", "Date of first diagnosis", "date",
      "C. Diagnosis & Tumour", required=True,
      help="أول تاريخ أثبت فيه الورم نسيجياً أو سريريّاً", width=16),
    F("date_of_first_symptom", "تاريخ أول عرض", "Date of first symptom", "date",
      "C. Diagnosis & Tumour", width=16),
    F("diagnosis_year", "سنة التشخيص", "Year of diagnosis", "integer",
      "C. Diagnosis & Tumour", help="يُحسب تلقائياً من تاريخ التشخيص", width=12),
    F("basis_of_diagnosis", "أساس التشخيص", "Basis of diagnosis (ICD-O-3)", "selection",
      "C. Diagnosis & Tumour", required=True, options=BASIS_OF_DIAGNOSIS,
      ref="ICD-O-3 field 10", width=24),
    F("primary_site", "موقع الورم الأولي (ICD-O-3)", "Primary site ICD-O-3 (T)", "char",
      "C. Diagnosis & Tumour", required=True, pattern=r"^C\d{2}(\.\d{1,2})?$",
      ref="ICD-O-3 Topography", help="C00.0 – C80.9", width=14),
    F("primary_site_label", "اسم الموقع الأولي", "Primary site description", "char",
      "C. Diagnosis & Tumour", help="يُعبّأ تلقائياً من جدول ICD-O-3", width=34),
    F("icd10_code", "ترميز ICD-10", "ICD-10 code", "char", "C. Diagnosis & Tumour",
      pattern=r"^[CD]\d{2}(\.\d{1,2})?$", ref="ICD-10 Chapter II",
      help="C00-D49 — يُشتق تلقائياً من ICD-O-3 عندما يكون ممكناً", width=12),
    F("laterality", "الجانبية", "Laterality", "selection", "C. Diagnosis & Tumour",
      options=LATERALITY, ref="ICD-O-3 field 5", width=14),
    F("morphology", "الفحص النسيجي (Morphology)", "Morphology ICD-O-3 (M)", "char",
      "C. Diagnosis & Tumour", required=True, pattern=r"^\d{4}/[0-369]$",
      ref="ICD-O-3 Morphology", help="مثال: 8070/3 سرطانة حرشفية", width=14),
    F("morphology_label", "اسم النسيج المرضي", "Morphology description", "char",
      "C. Diagnosis & Tumour", help="يُعبّأ تلقائياً من جدول ICD-O-3", width=40),
    F("behaviour", "السلوك (Behaviour)", "Behaviour code", "selection",
      "C. Diagnosis & Tumour", options=BEHAVIOUR, ref="ICD-O-3 field 5 suffix",
      help="يُشتق تلقائياً من آخر رمز في Morphology", width=22),
    F("histology_text", "نص التشخيص النسيجي (حرفي)", "Histology text (verbatim)", "text",
      "C. Diagnosis & Tumour", max_len=600,
      help="نص التشخيص كما ورد في تقرير التشريح المرضي — للمراجعة البشرية", width=48),
    F("grade", "درجة التمايز", "Histological grade", "selection", "C. Diagnosis & Tumour",
      options=GRADE, ref="ICD-O-3 field 6", width=26),
    F("multiple_primaries", "أورام أولية متعددة", "Multiple primaries", "boolean",
      "C. Diagnosis & Tumour", help="أكثر من ورم أولي مستقل في نفس المريض", width=14),
    F("primary_count", "عدد الأورام الأولية", "Number of primary tumours", "integer",
      "C. Diagnosis & Tumour", width=12),
    F("family_history", "تاريخ عائلي للسرطان", "Family history of cancer", "text",
      "C. Diagnosis & Tumour", max_len=300, width=30),
    F("risk_factors", "عوامل الخطورة", "Risk factors", "text", "C. Diagnosis & Tumour",
      max_len=400, help="تدخين، التهاب كبدي B/C، HPV، سمنة، تعرّض مهني…", width=34),

    # ---------------- D. التقسيم المرحلي TNM ----------------
    F("staging_system", "نظام التقسيم المرحلي", "Staging system", "selection",
      "D. Staging (TNM)", options=STAGING_SYSTEM, width=24),
    F("ct", "cT (سريري)", "Clinical T", "selection", "D. Staging (TNM)",
      options=T_STAGE, ref="AJCC 8th / UICC", width=10),
    F("cn", "cN (سريري)", "Clinical N", "selection", "D. Staging (TNM)",
      options=N_STAGE, width=10),
    F("cm", "cM (سريري)", "Clinical M", "selection", "D. Staging (TNM)",
      options=M_STAGE, width=10),
    F("clinical_stage", "المرحلة السريرية", "Clinical stage group", "selection",
      "D. Staging (TNM)", options=STAGE_GROUP, width=14),
    F("pt", "pT (نسيجي)", "Pathological T", "selection", "D. Staging (TNM)",
      options=T_STAGE, width=10),
    F("pn", "pN (نسيجي)", "Pathological N", "selection", "D. Staging (TNM)",
      options=N_STAGE, width=10),
    F("pm", "pM (نسيجي)", "Pathological M", "selection", "D. Staging (TNM)",
      options=M_STAGE, width=10),
    F("pathological_stage", "المرحلة النسيجية", "Pathological stage group", "selection",
      "D. Staging (TNM)", options=STAGE_GROUP, width=14),
    F("summary_stage", "المرحلة الموجزة (SEER)", "Summary stage", "selection",
      "D. Staging (TNM)", options=SUMMARY_STAGE,
      help="لازمة للتقارير الوطنية — موضعي / إقليمي / بعيد", width=20),
    F("stage_date", "تاريخ تحديد المرحلة", "Date of staging", "date", "D. Staging (TNM)",
      width=14),
    F("metastasis_sites", "مواقع الانتشار", "Metastatic sites", "text",
      "D. Staging (TNM)", max_len=300, width=28),
    F("biomarkers", "المؤشرات الحيوية", "Biomarkers (ER/PR/HER2/Ki67/PSA…)", "text",
      "D. Staging (TNM)", max_len=400, width=30),

    # ---------------- E. العلاج ----------------
    F("first_course_within_4m", "العلاج الأول خلال 4 أشهر", "First-course treatment ≤ 4 months",
      "boolean", "E. Treatment",
      help="معيار SEER/IARC: أي علاج أُعطي خلال 4 أشهر من التشخيص", width=16),
    F("treatment_centre", "مركز العلاج الرئيسي", "Main treatment centre", "selection",
      "E. Treatment", options=TREATMENT_CENTRES, width=28),
    F("treatment_summary", "ملخص العلاج", "Treatment summary (narrative)", "text",
      "E. Treatment", max_len=800, width=40),
    F("chemo_cycles", "عدد دورات العلاج الكيميائي", "Chemotherapy cycles", "integer",
      "E. Treatment", width=14),
    F("chemo_protocol", "بروتوكول العلاج الكيميائي", "Chemotherapy protocol", "char",
      "E. Treatment", help="مثال: FOLFOX-4، AC→T، CHOP، R-CHOP", width=24),
    F("radiotherapy_type", "نوع العلاج الإشعاعي", "Radiotherapy type", "selection",
      "E. Treatment", options=RADIOTHERAPY_TYPE, width=24),
    F("radiotherapy_dose", "الجرعة الإشعاعية الكلية (Gy)", "Total RT dose (Gy)", "char",
      "E. Treatment", help="مثال: 50 Gy / 25 جلسة", width=22),
    F("surgery_procedure", "نوع العملية الجراحية", "Surgical procedure", "char",
      "E. Treatment", max_len=200, width=30),
    F("treatment_response", "الاستجابة للعلاج", "Treatment response", "selection",
      "E. Treatment", options=TREATMENT_RESPONSE, width=22),
    F("surgery_performed", "أُجريت جراحة", "Surgery performed", "boolean",
      "E. Treatment", width=12),
    F("chemotherapy_given", "أُعطي علاج كيميائي", "Chemotherapy given", "boolean",
      "E. Treatment", width=12),
    F("radiotherapy_given", "أُعطي علاج إشعاعي", "Radiotherapy given", "boolean",
      "E. Treatment", width=12),
    F("hormonal_given", "أُعطي علاج هرموني", "Hormonal therapy given", "boolean",
      "E. Treatment", width=12),
    F("immunotherapy_given", "أُعطي علاج مناعي/موجّه", "Immuno/targeted therapy given",
      "boolean", "E. Treatment", width=14),

    # ---------------- F. المتابعة وحالة الحالة ----------------
    F("vitality_status", "حالة الحالة", "Vitality / follow-up status", "selection",
      "F. Follow-up & Outcome", required=True, options=VITALITY_STATUS, width=24),
    F("date_of_death", "تاريخ الوفاة", "Date of death", "date", "F. Follow-up & Outcome",
      help="إلزامي إذا كانت الحالة = متوفى", width=14),
    F("cause_of_death", "سبب الوفاة", "Underlying cause of death", "selection",
      "F. Follow-up & Outcome", options=CAUSE_OF_DEATH,
      help="إلزامي إذا كانت الحالة = متوفى", width=26),
    F("cause_of_death_icd10", "رمز ICD-10 لسبب الوفاة", "ICD-10 cause of death", "char",
      "F. Follow-up & Outcome", pattern=r"^[A-Z]\d{2}(\.\d{1,2})?$", width=16),
    F("death_age", "العمر عند الوفاة", "Age at death", "integer", "F. Follow-up & Outcome",
      width=12),
    F("survival_months", "مدة البقاء (بالأشهر)", "Survival (months)", "integer",
      "F. Follow-up & Outcome", help="يُحسب = (تاريخ الوفاة أو آخر متابعة) − تاريخ التشخيص",
      width=14),
    F("last_followup_date", "تاريخ آخر متابعة", "Last follow-up date", "date",
      "F. Follow-up & Outcome", width=16),
    F("last_disease_status", "حالة المرض عند آخر متابعة", "Disease status at last contact",
      "selection", "F. Follow-up & Outcome", options=DISEASE_STATUS_LAST, width=26),
    F("followup_source", "مصدر معلومات المتابعة", "Source of follow-up info", "char",
      "F. Follow-up & Outcome", help="سجل مدني، اتصال هاتفي، زيارة منزلية…", width=24),
    F("recurrence", "حدوث انتكاسة", "Recurrence", "boolean", "F. Follow-up & Outcome",
      width=12),
    F("recurrence_date", "تاريخ الانتكاسة", "Date of recurrence", "date",
      "F. Follow-up & Outcome", width=14),

    # ---------------- G. المستندات والتدقيق ----------------
    F("document_ids", "المستندات المرفقة", "Scanned documents", "one2many",
      "G. Documents & Audit", help="ملفات PDF/صور مسحوبة ضوئياً", export=False),
    F("document_count", "عدد المستندات", "No. of documents", "integer",
      "G. Documents & Audit", export=False, width=12),
    F("extraction_method", "طريقة الاستخراج", "Extraction method", "char",
      "G. Documents & Audit", export=False, width=18),
    F("extraction_confidence", "ثقة الاستخراج (%)", "Extraction confidence (%)", "float",
      "G. Documents & Audit", export=False, width=14),
    F("qc_status", "حالة جودة البيانات", "Data-quality status", "selection",
      "G. Documents & Audit", options=QC_STATUS, width=18),
    F("qc_score", "نقاط الجودة (0-100)", "QC score (0-100)", "integer",
      "G. Documents & Audit", width=14),
    F("qc_issues", "ملاحظات الجودة", "QC issues found", "text",
      "G. Documents & Audit", max_len=2000, width=50),
    F("data_entry_status", "حالة إدخال البيانات", "Record status", "selection",
      "G. Documents & Audit", options=DATA_ENTRY_STATUS, width=20),
    F("validated_by", "اعتمده", "Validated by", "char", "G. Documents & Audit", width=20),
    F("validated_on", "تاريخ الاعتماد", "Validation date", "date", "G. Documents & Audit",
      width=14),
    F("created_on", "تاريخ الإنشاء", "Created on", "datetime", "G. Documents & Audit",
      export=False),
    F("written_on", "آخر تعديل", "Last modified", "datetime", "G. Documents & Audit",
      export=False),
]

FIELDS = OrderedDict((f["name"], f) for f in DATA_DICTIONARY)

GROUPS = OrderedDict()
for _f in DATA_DICTIONARY:
    GROUPS.setdefault(_f["group"], []).append(_f["name"])

REQUIRED_FIELDS = [f["name"] for f in DATA_DICTIONARY if f["required"]]

# الأعمدة التي تُصدَّر إلى Excel بالترتيب
EXCEL_COLUMNS = [f["name"] for f in DATA_DICTIONARY if f["export"]]


def label(name, lang="ar"):
    """اسم الحقل بلغة معيّنة."""
    f = FIELDS.get(name)
    if not f:
        return name
    return f["label_ar"] if lang == "ar" else f["label_en"]


def option_label(field_name, value, lang="ar"):
    """ترجمة قيمة قائمة اختيار."""
    f = FIELDS.get(field_name)
    if not f or not f["options"]:
        return value or ""
    pair = f["options"].get(str(value))
    if not pair:
        return value or ""
    return pair[0] if lang == "ar" else pair[1]


def options_table(name):
    """يعيد جدول خيارات باسمه.

    يقبل إما اسم حقل في القاموس (``sex``) أو اسم جدول عام
    (``treatment_modality`` → ``TREATMENT_MODALITY``) — الجداول العامة تُستخدم
    في أسطر العلاج التفصيلية التي ليست حقولاً في سجل الحالة نفسه.
    """
    f = FIELDS.get(name)
    if f and f.get("options"):
        return f["options"]
    const = name.upper()
    table = globals().get(const)
    if isinstance(table, dict):
        return table
    return {}


def option_pairs(field_name, lang="ar_AR"):
    """[(key, label)] بلغة أودو — تُستخدم في Selection fields."""
    ar = not lang.startswith("en")
    opts = options_table(field_name)
    return [(k, (v[0] if ar else v[1])) for k, v in opts.items()]


def option_values(field_name):
    f = FIELDS.get(field_name)
    return list(f["options"].keys()) if f and f["options"] else []


def fields_in_group(group):
    return [FIELDS[n] for n in GROUPS.get(group, [])]


def odoo_field_definition(name):
    """
    يولّد تعريف حقل أودو Python من القاموس.
    يستخدمه سكربت build_odoo_models.py لضمان التطابق التام بين الأداة والوحدة.
    """
    f = FIELDS[name]
    t = f["type"]
    if t == "char":
        return ("Char", f'string="{f["label_ar"]}", size={f["max_len"]}, '
                        f'required={f["required"]}, translate=True')
    if t == "text":
        return ("Text", f'string="{f["label_ar"]}", required={f["required"]}, translate=True')
    if t == "date":
        return ("Date", f'string="{f["label_ar"]}", required={f["required"]}')
    if t == "datetime":
        return ("Datetime", f'string="{f["label_ar"]}", readonly=True')
    if t == "integer":
        return ("Integer", f'string="{f["label_ar"]}"')
    if t == "float":
        return ("Float", f'string="{f["label_ar"]}", digits=(5,2)')
    if t == "boolean":
        return ("Boolean", f'string="{f["label_ar"]}"')
    if t == "binary":
        return ("Binary", f'string="{f["label_ar"]}", attachment=True')
    if t == "selection":
        return ("Selection", f'selection="_selection_{name}", string="{f["label_ar"]}", '
                             f'required={f["required"]}, translate=True')
    if t == "one2many":
        return ("One2many", f'"cancer.registry.document", "case_id", string="{f["label_ar"]}"')
    return ("Char", f'string="{f["label_ar"]}"')


if __name__ == "__main__":
    print(f"إجمالي الحقول: {len(FIELDS)}")
    print(f"الحقول الإلزامية: {len(REQUIRED_FIELDS)}")
    for g, names in GROUPS.items():
        print(f"  {g:32s} {len(names):3d} حقل")

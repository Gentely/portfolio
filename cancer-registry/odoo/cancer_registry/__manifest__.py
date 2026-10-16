# -*- coding: utf-8 -*-
{
    "name": "السجل القومي للسرطان — Cancer Registry",
    "summary": "تبليغ، استخراج آلي (OCR)، ترميز ICD-O-3/TNM، فحص جودة، وأرشفة لحالات السرطان",
    "description": """
وحدة «السجل القومي للسرطان»
============================

مبنية لمكتب سجل السرطان — المعهد القومي للأورام، صبراتة، ليبيا.

المسار الكامل للحالة داخل الوحدة:

    مستند ورقي ممسوح ضوئياً
        ↓  زر «رفع مستند ممسوح ضوئياً / PDF»
    أرشفة في نظام المستندات (DMS) مع بصمة SHA-256 ومنع التكرار
        ↓  زر «التلخيص والاستخراج الذكي»  (OCR: Tesseract عربي+إنجليزي / نص PDF / Azure AI)
    تفريغ آلي في حقول القاموس مع دليل لكل حقل ونسبة ثقة
        ↓  زر «فحص جودة البيانات»
    ~40 قاعدة: الاكتمال، صيغة ICD-O-3، ترميز TNM/المرحلة، تناقض التواريخ
    والجرعات، توافق الجنس مع الموقع، كشف السجلات المكررة
        ↓  زر «حفظ / تصدير»
    ملف Excel مطابق لقالب السجل الوطني (6 أوراق) + أرشيف PDF

المعايير المستخدمة
------------------
* ICD-O-3  (Topography + Morphology) — منظمة الصحة العالمية / IARC
* ICD-10   للفصل الثاني (الأورام) — تُشتق تلقائياً من ICD-O-3
* TNM 8th  (UICC/AJCC) مع 156 قاعدة اشتقاق مرحلة
* SEER Summary Stage
* IARC/ENCR — قواعد جودة بيانات السجلات السكانية
* حقول محلية ليبية: الرقم الوطني (12 رقماً)، البلديات الـ22، مراكز العلاج

قاموس الحقول
------------
86 حقلاً في 7 مجموعات (A–G) مُعرَّفة في مكان واحد:
``crcore/dictionary.py`` — وهو **نفس** القاموس الذي تستخدمه الأداة المستقلة
(واجهة المتصفح + سطر الأوامر) ونفس ترتيب أعمدة ملف Excel المُصدَّر.

لتجديد ملفات الوحدة بعد تعديل القاموس::

    python3 tools/build_odoo_addon.py

المتطلبات الخارجية (اختيارية)
-----------------------------
* ``tesseract-ocr`` + حزمة اللغة العربية — لقراءة المستندات الممسوحة ضوئياً.
  بدونها تعمل الوحدة بالكامل على ملفات PDF النصية والإدخال اليدوي.
* ``poppler-utils`` (pdftoppm) — لتحويل صفحات PDF إلى صور قبل OCR.
* ``openpyxl`` — للتصدير إلى Excel (مثبَّت مسبقاً مع أودو).
""",
    "version": "17.0.1.0.0",
    "category": "Medical/Health",
    "author": "Mohamed Ahmed Bahur — مكتب سجل السرطان، المعهد القومي للأورام، صبراتة",
    "website": "https://github.com/Gentely/portfolio",
    "license": "LGPL-3",
    "sequence": 10,
    "depends": ["base", "web", "mail"],
    "data": [
        # الأمان أولاً
        "security/cancer_registry_security.xml",
        "security/ir.model.access.csv",
        # البيانات المرجعية والتسلسلات
        "data/ir_sequence_data.xml",
        "data/icdo3_topography_data.xml",
        "data/icdo3_morphology_data.xml",
        # المعالجات (Wizards)
        "wizards/extract_wizard_views.xml",
        "wizards/qc_wizard_views.xml",
        "wizards/export_wizard_views.xml",
        # الواجهات
        "views/cancer_registry_case_views.xml",
        "views/cancer_registry_document_views.xml",
        "views/cancer_registry_treatment_views.xml",
        "views/cancer_registry_refdata_views.xml",
        "views/cancer_registry_report_views.xml",
        "views/cancer_registry_menus.xml",
    ],
    "demo": [],
    "application": True,
    "installable": True,
    "auto_install": False,
    "images": ["static/description/banner.png"],
    "support": "Cancer Registry Office — National Cancer Institute, Sabratha",
    "contributors": ["Mohamed Ahmed Bahur"],
}

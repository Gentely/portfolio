# -*- coding: utf-8 -*-
"""
النواة المشتركة لسجل السرطان — Cancer Registry Core
====================================================
لا تعتمد على أودو ولا على أي إطار عمل: بايثون خالص.
نفس هذه الوحدة تُستخدم في:
  • الأداة المستقلة (webapp + cli)
  • وحدة أودو (odoo/cancer_registry) عبر استيراد مباشر

الوحدات:
  dictionary  قاموس الحقول والقوائم المرجعية (مصدر الحقيقة)
  reference   جداول ICD-O-3 / ICD-10 / TNM
  ocr         قراءة المستندات المسحوبة ضوئياً
  extractor   استخراج الحقول من النص
  quality     فحص جودة البيانات
  excel_export التصدير إلى Excel
  storage     التخزين وسجل التدقيق
  pipeline    الربط بين كل ما سبق
"""

__version__ = "1.0.0"
__author__ = "Cancer Registry Office — NCI Sabratha"

from . import dictionary, reference, ocr, extractor, quality, storage  # noqa: F401

__all__ = ["dictionary", "reference", "ocr", "extractor", "quality",
           "excel_export", "storage", "pipeline", "__version__"]

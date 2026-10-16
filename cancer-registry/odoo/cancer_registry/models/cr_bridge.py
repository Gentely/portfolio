# -*- coding: utf-8 -*-
"""
جسر إلى نواة سجل السرطان (crcore)
==================================
يبحث عن crcore بالترتيب:
  1) متغيّر البيئة  CR_CORE_PATH
  2) النسخة المضمّنة داخل الوحدة  ./crcore
  3) مجلد المستودع  ../../crcore

بهذا تعمل الوحدة سواء نُشرت مستقلة (addons path) أو من داخل المستودع.
"""
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent          # …/cancer_registry/models
_ADDON = _HERE.parent                             # …/cancer_registry
_CANDIDATES = [
    os.getenv("CR_CORE_PATH"),                    # 1) مسار صريح من البيئة
    str(_ADDON / "crcore"),                       # 2) النسخة المضمّنة في الوحدة
    str(_ADDON.parent.parent / "crcore"),         # 3) مجلد المستودع (أثناء التطوير)
    str(Path.cwd() / "crcore"),                   # 4) مجلد العمل الحالي
]

for _c in _CANDIDATES:
    if _c and (Path(_c) / "dictionary.py").exists():
        _root = str(Path(_c).parent)
        if _root not in sys.path:
            sys.path.insert(0, _root)
        break
else:                                                     # pragma: no cover
    raise ImportError(
        "تعذّر العثور على crcore. انسخ مجلد crcore داخل وحدة cancer_registry، "
        "أو اضبط متغير البيئة CR_CORE_PATH على مساره.")

from crcore import (dictionary, excel_export, extractor, ocr, pipeline,  # noqa: E402
                    quality, reference, storage)

__all__ = ["dictionary", "excel_export", "extractor", "ocr", "pipeline",
           "quality", "reference", "storage"]

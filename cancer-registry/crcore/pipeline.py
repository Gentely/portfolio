# -*- coding: utf-8 -*-
"""
خط المعالجة الكامل — Pipeline
==============================
المسار الذي يسلكه كل سجل، من الورقة المسحوبة إلى صف في Excel:

   مستند ممسوح  →  OCR  →  استخراج الحقول  →  فحص الجودة  →  حفظ + تدقيق  →  Excel
      (1)          (2)          (3)              (4)              (5)          (6)

استخدم:
    from crcore.pipeline import process_file, process_batch, run_qc, export_all
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path

from . import ocr, extractor, quality, storage, reference
from .dictionary import FIELDS

log = logging.getLogger("crcore.pipeline")


# ==========================================================================
#  خطوة 2+3: مستند → نص → حقول
# ==========================================================================
def read_and_extract(file_path, prefer: str = "auto", lang: str = "ara+eng",
                     manual_text: str = "", hints: dict = None) -> dict:
    """
    يقرأ ملفاً ويستخرج الحقول. يعيد:
      {"ocr": OCRResult-dict, "extraction": ExtractionResult-dict, "record": {...}}
    """
    ocr_res = ocr.read_document(file_path, prefer=prefer, lang=lang,
                                manual_text=manual_text)
    ext = extractor.extract(ocr_res.text, engine=ocr_res.engine,
                            ocr_confidence=ocr_res.confidence, hints=hints or {})
    if ocr_res.needs_manual:
        ext.warnings.extend(ocr_res.warnings)

    record = dict(ext.values)
    # اسم الملف غالباً يحمل الرقم الوطني أو رقم الملف → استغلاله
    stem = Path(str(file_path)).stem
    if not record.get("national_id"):
        import re
        m = re.search(r"(?<!\d)(\d{12})(?!\d)", stem)
        if m:
            record["national_id"] = m.group(1)
    if not record.get("medical_file_no"):
        import re
        m = re.search(r"(?:file|ملف|mrn)\s*[-_#]?\s*([A-Za-z0-9\-]{3,20})", stem, re.I)
        if m:
            record["medical_file_no"] = m.group(1)

    return {
        "ocr": ocr_res.to_dict(),
        "extraction": ext.to_dict(),
        "record": record,
    }


# ==========================================================================
#  خطوة 4: فحص الجودة
# ==========================================================================
def run_qc(record: dict, with_duplicates: bool = True) -> dict:
    """يفحص سجلاً واحداً ويعيد التقرير كـ dict."""
    dupes = storage.duplicate_keys(exclude=record.get("registry_no", "")) \
        if with_duplicates else set()
    rep = quality.check_case(record, duplicates=dupes)
    return rep.to_dict()


# ==========================================================================
#  خطوة 5: مستند واحد → سجل محفوظ
# ==========================================================================
def process_file(file_path, registry_no: str = "", prefer: str = "auto",
                 lang: str = "ara+eng", manual_text: str = "",
                 keep_document: bool = True, run_quality: bool = True,
                 save: bool = True, existing: dict = None) -> dict:
    """
    يعالج ملفاً واحداً من البداية إلى النهاية.

    يعيد dict فيه:
      registry_no, record, qc, extraction, ocr, document, saved, path
    """
    file_path = Path(file_path)
    result = read_and_extract(file_path, prefer=prefer, lang=lang,
                              manual_text=manual_text)
    record = dict(existing or {})
    record = extractor.merge(record, _ExtractionShim(result["extraction"]),
                             overwrite=not bool(existing))

    if not record.get("registry_no"):
        record["registry_no"] = registry_no or storage.next_registry_no()
    record["registry_no"] = registry_no or record["registry_no"]

    # سنة التشخيص تُحدد مجلد الأرشيف
    dod = extractor.parse_date(record.get("date_of_diagnosis"))
    year = dod.year if dod else date.today().year

    document = None
    if keep_document:
        try:
            document = storage.store_document(file_path, record["registry_no"], year=year)
        except Exception as exc:
            log.warning("تعذّر أرشفة المستند: %s", exc)
            document = {"error": str(exc)}

    docs = storage.list_documents(record["registry_no"])
    record["document_count"] = len(docs)
    record["extraction_method"] = result["ocr"]["engine"]
    record["extraction_confidence"] = result["extraction"]["confidence"]
    if not record.get("data_entry_status"):
        record["data_entry_status"] = "extracted"
    if not record.get("created_on"):
        record["created_on"] = datetime.now().isoformat(timespec="seconds")

    qc_report = run_qc(record) if run_quality else {}
    if qc_report:
        record["qc_status"] = qc_report["status"]
        record["qc_score"] = qc_report["score"]

    saved = None
    if save:
        saved = storage.save_case(record, treatments=[], documents=docs,
                                  qc_report=qc_report, extraction=result["extraction"])
        record = saved

    return {
        "registry_no": record["registry_no"],
        "record": record,
        "qc": qc_report,
        "extraction": result["extraction"],
        "ocr": result["ocr"],
        "document": document,
        "documents": docs,
        "archive_path": storage.archive_url(record["registry_no"]),
        "saved": bool(saved),
        "file": file_path.name,
    }


class _ExtractionShim:
    """يجعل dict الاستخراج متوافقاً مع extractor.merge."""
    def __init__(self, ext_dict):
        self.values = ext_dict.get("values", {})
        self.hits = {}


# ==========================================================================
#  معالجة دُفعة
# ==========================================================================
SUPPORTED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".txt"}


def process_batch(paths, prefer: str = "auto", lang: str = "ara+eng",
                  progress=None, save: bool = True) -> dict:
    """
    يعالج قائمة ملفات (أو مجلداً) بالتتابع.
    progress: callable(i, total, filename, result)
    """
    files = _collect_files(paths)
    results, failures = [], []
    for i, fp in enumerate(files, start=1):
        try:
            r = process_file(fp, prefer=prefer, lang=lang, save=save)
            results.append(r)
        except Exception as exc:
            log.exception("فشل معالجة %s", fp)
            failures.append({"file": str(fp), "error": str(exc)})
        if progress:
            progress(i, len(files), Path(fp).name,
                     results[-1] if results and results[-1]["file"] == Path(fp).name else None)

    # فحص الدفعة كاملة (يكشف التكرار عبر السجلات)
    records = [r["record"] for r in results]
    batch_qc = quality.check_batch(records) if records else {"total": 0, "by_status": {},
                                                             "avg_score": 0, "duplicates": [],
                                                             "top_issues": [], "issues": [],
                                                             "reports": []}
    return {
        "processed": len(results),
        "failed": len(failures),
        "failures": failures,
        "results": results,
        "batch_qc": {k: v for k, v in batch_qc.items() if k != "reports"},
        "started": datetime.now().isoformat(timespec="seconds"),
    }


def _collect_files(paths) -> list:
    out = []
    if isinstance(paths, (str, Path)):
        paths = [paths]
    for p in paths:
        p = Path(p)
        if p.is_dir():
            out += sorted([str(x) for x in p.rglob("*")
                           if x.is_file() and x.suffix.lower() in SUPPORTED_SUFFIXES])
        elif p.is_file():
            out.append(str(p))
        else:
            log.warning("مسار غير موجود: %s", p)
    # إزالة التكرار
    seen, uniq = set(), []
    for f in out:
        if f not in seen:
            seen.add(f)
            uniq.append(f)
    return uniq


# ==========================================================================
#  خطوة 6: التصدير
# ==========================================================================
def export_all(out_path=None, only_validated: bool = False, meta: dict = None,
               include_qc: bool = True) -> str:
    """يصدر كل السجلات المحفوظة إلى Excel."""
    from . import excel_export

    cases = storage.all_cases()
    if only_validated:
        cases = [c for c in cases if c["case"].get("data_entry_status") == "validated"]
    records = []
    for doc in cases:
        rec = dict(doc["case"])
        rec["_treatments"] = doc.get("treatments") or []
        rec["_documents"] = doc.get("documents") or []
        records.append(rec)

    if not records:
        raise ValueError("لا توجد سجلات محفوظة للتصدير")

    out = Path(out_path or (storage.export_dir() / excel_export.default_filename()))
    path = excel_export.export_records(records, out, meta=meta or {}, include_qc=include_qc)
    storage.audit("export.excel", details={
        "path": path, "records": len(records), "only_validated": only_validated})
    return path


def export_case(registry_no: str, out_path=None) -> str:
    from . import excel_export
    doc = storage.load_case(registry_no)
    if not doc:
        raise ValueError(f"لا يوجد سجل بالرقم {registry_no}")
    rec = dict(doc["case"])
    rec["_treatments"] = doc.get("treatments") or []
    out = Path(out_path or (storage.export_dir() /
                            f"{registry_no.replace('/', '_')}.xlsx"))
    return excel_export.export_records([rec], out)


# ==========================================================================
#  نظرة عامة
# ==========================================================================
def dashboard() -> dict:
    """أرقام تُعرض في أعلى واجهة الأداة."""
    st = storage.stats()
    st["engines"] = ocr.engine_status()
    st["refdata"] = reference.stats()
    st["version"] = "1.0.0"
    st["storage_dir"] = str(storage.BASE_DIR)
    return st


if __name__ == "__main__":
    print(json.dumps(dashboard(), ensure_ascii=False, indent=2, default=str))

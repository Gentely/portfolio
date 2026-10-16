# -*- coding: utf-8 -*-
"""
التخزين وسجل التدقيق — Storage & Audit Trail
=============================================
بنية بسيطة على نظام الملفات (بدون قاعدة بيانات) كي تعمل الأداة على أي جهاز:

  storage/
    cases/<registry_no>.json        سجل الحالة كاملاً
    index.json                      فهرس سريع للبحث والتكرار
    documents/<year>/<registry_no>/  الملفات الأصلية الممسوحة ضوئياً
    audit.jsonl                      سجل تدقيق زمني لكل إجراء (append-only)
    exports/                         ملفات Excel/PDF المصدَّرة
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
from datetime import date, datetime
from pathlib import Path

from . import reference as ref
from .extractor import parse_date, iso

BASE_DIR = Path(os.getenv("CR_STORAGE_DIR",
                          Path(__file__).resolve().parent.parent / "storage"))

_LOCK = threading.RLock()


def init_storage(base: Path = None) -> Path:
    b = Path(base) if base else BASE_DIR
    for sub in ("cases", "documents", "exports", "audit"):
        (b / sub).mkdir(parents=True, exist_ok=True)
    if not (b / "index.json").exists():
        (b / "index.json").write_text("{}", encoding="utf-8")
    return b


def base_dir() -> Path:
    return init_storage()


# ==========================================================================
#  سجل التدقيق
# ==========================================================================
def audit(action: str, registry_no: str = "", user: str = "registry_officer",
          details: dict = None):
    """
    يكتب سطراً واحداً في audit.jsonl — لا يُحذف ولا يُعدَّل أبداً.
    (مطلوب في تدقيقات IARC/ENCR وعند التساؤل عن مصدر أي قيمة)
    """
    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "action": action,
        "registry_no": registry_no,
        "user": user,
        "details": details or {},
    }
    with _LOCK:
        init_storage()
        with (BASE_DIR / "audit.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def audit_trail(registry_no: str, limit: int = 200) -> list:
    out = []
    path = BASE_DIR / "audit.jsonl"
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not registry_no or e.get("registry_no") == registry_no:
                out.append(e)
    return out[-limit:][::-1]


# ==========================================================================
#  الملفات الممسوحة ضوئياً
# ==========================================================================
def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def document_dir(registry_no: str, year=None, create: bool = True) -> Path:
    """مسار أرشفة مستندات سجل:  documents/<سنة>/<رقم السجل>/

    ``create=False`` يعيد المسار دون إنشائه — للاستعلامات فقط، حتى لا
    تتراكم مجلدات فارغة في الأرشيف.
    """
    y = year or str(date.today().year)
    d = BASE_DIR / "documents" / str(y) / registry_no
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def store_document(src_path, registry_no: str, original_name: str = None,
                   year=None) -> dict:
    """ينسخ الملف إلى الأرشيف ويعيد سجله الوصفي."""
    src = Path(src_path)
    if not src.exists():
        raise FileNotFoundError(src)
    digest = sha256(src)
    name = original_name or src.name
    d = document_dir(registry_no, year)
    # منع التكرار بالـ hash
    existing = find_document_by_hash(digest, registry_no)
    if existing:
        return {**existing, "duplicate": True}

    safe = "".join(c for c in name if c.isalnum() or c in "._- ")[:80].strip()
    dest = d / f"{digest[:12]}_{safe}"
    shutil.copy2(src, dest)
    rec = {
        "id": digest[:16],
        "filename": name,
        "stored_path": str(dest),
        "sha256": digest,
        "size": dest.stat().st_size,
        "uploaded_on": datetime.now().isoformat(timespec="seconds"),
        "mime": _guess_mime(dest.suffix.lower()),
        "duplicate": False,
    }
    audit("document.upload", registry_no,
          details={"filename": name, "sha256": digest, "size": rec["size"]})
    return rec


def find_document_by_hash(digest: str, registry_no: str = None):
    """يبحث عن ملف ببصمته في **كل** سنوات الأرشيف.

    خطأ سابق: كان البحث مقتصراً على مجلد سنة الرفع الحالية، فيُخزَّن الملف
    مرة ثانية إن كان مؤرشفاً تحت سنة تشخيص أقدم. الآن البحث شامل.
    """
    root = BASE_DIR / "documents"
    if not root.exists():
        return None
    for p in sorted(root.rglob(f"{digest[:12]}_*")):
        if not p.is_file():
            continue
        if registry_no and not str(p.parent).endswith(registry_no):
            continue
        return {"stored_path": str(p), "filename": p.name, "sha256": digest,
                "size": p.stat().st_size if p.exists() else 0}
    return None


def list_documents(registry_no: str) -> list:
    root = BASE_DIR / "documents"
    out = []
    if not root.exists():
        return out
    for p in sorted(root.rglob("*")):
        if p.is_file() and f"/{registry_no}/" in p.as_posix() + "/":
            out.append({
                "filename": p.name,
                "stored_path": str(p),
                "size": p.stat().st_size,
                "uploaded_on": datetime.fromtimestamp(p.stat().st_ctime).isoformat(timespec="seconds"),
                "mime": _guess_mime(p.suffix.lower()),
            })
    return out


def archive_url(registry_no: str) -> str:
    """المسار البشري المقروء لمجلد الأرشيف (يُعرض خلف زر «مكان الملف المخزن»)."""
    root = BASE_DIR / "documents"
    hits = sorted([p for p in root.rglob(registry_no) if p.is_dir()]) if root.exists() else []
    if hits:
        return str(hits[-1])
    return str(document_dir(registry_no))


def _guess_mime(suffix: str) -> str:
    return {
        ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg", ".tif": "image/tiff", ".tiff": "image/tiff",
        ".txt": "text/plain", ".json": "application/json",
    }.get(suffix, "application/octet-stream")


# ==========================================================================
#  السجلات (JSON)
# ==========================================================================
def next_registry_no(prefix: str = "CR", year: int = None) -> str:
    """CR2026/0007 — تسلسل سنوي بدون فجوات."""
    y = year or date.today().year
    with _LOCK:
        idx = _load_index()
        seq = idx.get(f"_seq_{prefix}{y}", 0) + 1
        idx[f"_seq_{prefix}{y}"] = seq
        _save_index(idx)
    return f"{prefix}{y}/{seq:04d}"


def _index_path() -> Path:
    return BASE_DIR / "index.json"


def _load_index() -> dict:
    init_storage()
    try:
        return json.loads(_index_path().read_text(encoding="utf-8") or "{}")
    except (json.JSONDecodeError, OSError):
        return {}


def _save_index(idx: dict):
    _index_path().write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")


def _index_entry(rec: dict) -> dict:
    """حقول خفيفة تُخزَّن في الفهرس للبحث السريع وكشف التكرار."""
    return {
        "registry_no": rec.get("registry_no", ""),
        "national_id": rec.get("national_id", ""),
        "full_name": rec.get("full_name", "") or " ".join(
            filter(None, [rec.get("first_name", ""), rec.get("father_name", ""),
                          rec.get("family_name", "")])),
        "sex": rec.get("sex", ""),
        "age": rec.get("age_at_diagnosis", ""),
        "summary_stage": rec.get("summary_stage", ""),
        "reporting_facility": rec.get("reporting_facility", ""),
        "primary_site": rec.get("primary_site", ""),
        "site_label": ref.site_label(ref.normalise_site(rec.get("primary_site", ""))),
        "morphology": rec.get("morphology", ""),
        "date_of_diagnosis": rec.get("date_of_diagnosis", ""),
        "vitality_status": rec.get("vitality_status", ""),
        "qc_status": rec.get("qc_status", ""),
        "qc_score": rec.get("qc_score", ""),
        "data_entry_status": rec.get("data_entry_status", ""),
        "district": rec.get("district", ""),
        "updated_on": datetime.now().isoformat(timespec="seconds"),
        "dup_key": "|".join([
            str(rec.get("national_id") or ""),
            ref.normalise_site(str(rec.get("primary_site") or "")),
            str(rec.get("date_of_diagnosis") or "")]),
    }


def save_case(record: dict, treatments: list = None, documents: list = None,
              qc_report: dict = None, extraction: dict = None) -> dict:
    """يحفظ السجل ويحدّث الفهرس ويسجّل التدقيق."""
    with _LOCK:
        rec = dict(record)
        if not rec.get("registry_no"):
            rec["registry_no"] = next_registry_no()
        if not rec.get("created_on"):
            rec["created_on"] = datetime.now().isoformat(timespec="seconds")
        rec["written_on"] = datetime.now().isoformat(timespec="seconds")

        if qc_report:
            rec["qc_status"] = qc_report.get("status", rec.get("qc_status"))
            rec["qc_score"] = qc_report.get("score", rec.get("qc_score"))
            rec["qc_issues"] = "\n".join(
                f"[{i.get('severity')}] {i.get('code')} {i.get('message')}"
                for i in qc_report.get("issues", []))
        if extraction:
            rec["extraction_method"] = extraction.get("engine", "")
            rec["extraction_confidence"] = extraction.get("confidence", 0)

        doc = {
            "case": rec,
            "treatments": treatments or rec.get("_treatments") or [],
            "documents": documents or rec.get("_documents") or [],
            "qc": qc_report or {},
            "extraction": extraction or {},
        }
        path = BASE_DIR / "cases" / f"{rec['registry_no'].replace('/', '_')}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=str),
                        encoding="utf-8")

        idx = _load_index()
        cases = idx.setdefault("cases", {})
        cases[rec["registry_no"]] = _index_entry(rec)
        _save_index(idx)

        audit("case.save", rec["registry_no"],
              details={"path": str(path), "qc": rec.get("qc_status"),
                       "fields_filled": len([k for k, v in rec.items() if v not in ("", None)])})
        rec["_path"] = str(path)
        return rec


def load_case(registry_no: str) -> dict:
    path = BASE_DIR / "cases" / f"{registry_no.replace('/', '_')}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def all_cases() -> list:
    d = BASE_DIR / "cases"
    out = []
    if not d.exists():
        return out
    for p in sorted(d.glob("*.json")):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
            doc["case"]["_path"] = str(p)
            out.append(doc)
        except (json.JSONDecodeError, OSError):
            continue
    return out


def search(query: str = "", district: str = "", year: str = "",
           site_prefix: str = "", sex: str = "", status: str = "", limit: int = 500) -> list:
    """بحث سريع في الفهرس (بدون تحميل كل الملفات)."""
    idx = _load_index().get("cases", {})
    q = (query or "").strip().lower()
    out = []
    for no, e in idx.items():
        if q and q not in json.dumps(e, ensure_ascii=False).lower():
            continue
        if district and e.get("district") != district:
            continue
        if year and not str(e.get("date_of_diagnosis", "")).startswith(str(year)):
            continue
        if site_prefix and not str(e.get("primary_site", "")).upper().startswith(site_prefix.upper()):
            continue
        if sex and e.get("sex") != sex:
            continue
        if status and e.get("qc_status") != status:
            continue
        out.append(e)
        if len(out) >= limit:
            break
    return out


def duplicate_keys(exclude: str = "") -> set:
    """مفاتيح التكرار الموجودة — تُمرَّر إلى محرك الجودة."""
    idx = _load_index().get("cases", {})
    return {e.get("dup_key") for no, e in idx.items()
            if no != exclude and e.get("dup_key") and e["dup_key"].strip("|")}


def delete_case(registry_no: str) -> bool:
    with _LOCK:
        path = BASE_DIR / "cases" / f"{registry_no.replace('/', '_')}.json"
        idx = _load_index()
        idx.get("cases", {}).pop(registry_no, None)
        _save_index(idx)
        audit("case.delete", registry_no)
        if path.exists():
            path.unlink()
            return True
        return False


def export_dir() -> Path:
    d = BASE_DIR / "exports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def stats() -> dict:
    idx = _load_index().get("cases", {})
    cases = list(idx.values())
    by_site, by_district, by_sex, by_qc, by_year = {}, {}, {}, {}, {}
    for e in cases:
        by_site[e.get("site_label") or e.get("primary_site") or "غير محدد"] = \
            by_site.get(e.get("site_label") or e.get("primary_site") or "غير محدد", 0) + 1
        by_district[e.get("district") or "غير محدد"] = by_district.get(e.get("district") or "غير محدد", 0) + 1
        by_sex[e.get("sex") or "غير محدد"] = by_sex.get(e.get("sex") or "غير محدد", 0) + 1
        by_qc[e.get("qc_status") or "not_run"] = by_qc.get(e.get("qc_status") or "not_run", 0) + 1
        y = str(e.get("date_of_diagnosis") or "")[:4] or "غير معروف"
        by_year[y] = by_year.get(y, 0) + 1
    n_docs = sum(1 for p in (BASE_DIR / "documents").rglob("*") if p.is_file()) \
        if (BASE_DIR / "documents").exists() else 0
    return {
        "total_cases": len(cases),
        "total_documents": n_docs,
        "by_site": dict(sorted(by_site.items(), key=lambda x: -x[1])),
        "by_district": dict(sorted(by_district.items(), key=lambda x: -x[1])),
        "by_sex": by_sex,
        "by_qc_status": by_qc,
        "by_year": dict(sorted(by_year.items())),
        "avg_qc_score": round(sum(float(e.get("qc_score") or 0) for e in cases) / len(cases), 1)
                        if cases else 0,
    }

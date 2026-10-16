# -*- coding: utf-8 -*-
"""
واجهة سجل السرطان المستقلة — تعمل بدون أودو
=============================================
خادم محلي صغير (Flask) يقدّم نفس خط المعالجة:

   رفع المستند  →  معاينة جنباً إلى جنب  →  استخراج  →  جودة  →  حفظ  →  Excel

التشغيل:
    python3 run.py                ثم افتح http://localhost:8765
    python3 run.py --port 9000 --host 0.0.0.0

لا يحتاج قاعدة بيانات: كل شىء داخل مجلد storage/
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from datetime import date, datetime
from pathlib import Path

# السماح بالتشغيل من أى مكان
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flask import (Flask, jsonify, render_template, request, send_file,
                   send_from_directory, abort, Response)

from crcore import dictionary as dic
from crcore import extractor, ocr, pipeline, quality, reference, storage
from crcore.dictionary import (DATA_DICTIONARY, FIELDS, GROUPS, option_label)

app = Flask(__name__, template_folder=str(Path(__file__).parent / "templates"),
            static_folder=str(Path(__file__).parent / "static"))
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024      # 200 MB
app.config["JSON_AS_ASCII"] = False

storage.init_storage()

UPLOAD_TMP = Path(tempfile.gettempdir()) / "cr_uploads"
UPLOAD_TMP.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------
# أدوات مساعدة
# --------------------------------------------------------------------------
def _jresp(**kw):
    r = jsonify(kw)
    r.headers["Content-Type"] = "application/json; charset=utf-8"
    return r


def _case_payload(doc: dict) -> dict:
    """يجهّز السجل للعرض: يترجم القوائم ويضيف أسماء التسميات."""
    rec = dict(doc.get("case", {}))
    view = {}
    for name, val in rec.items():
        f = FIELDS.get(name)
        if not f:
            continue
        view[name] = {
            "value": "" if val is None else str(val),
            "display": _fmt_display(name, val),
            "label_ar": f["label_ar"],
            "label_en": f["label_en"],
            "type": f["type"],
            "required": f["required"],
            "help": f["help_ar"],
            "options": ([{"key": k, "ar": v[0], "en": v[1]} for k, v in f["options"].items()]
                        if f["options"] else None),
        }
    return view


def _fmt_display(name: str, val) -> str:
    if val in (None, ""):
        return ""
    f = FIELDS.get(name, {})
    if f.get("type") == "selection":
        return option_label(name, str(val), "ar")
    if f.get("type") == "boolean":
        return "نعم" if str(val).lower() in ("true", "1", "yes", "نعم") else "لا"
    return str(val)


def _ordered_record(raw: dict) -> dict:
    """يرتّب حقول السجل حسب ترتيب القاموس ويحذف المفاتيح الداخلية."""
    return {k: raw.get(k) for k in FIELDS if k in raw and not k.startswith("_")}


# --------------------------------------------------------------------------
# الصفحات
# --------------------------------------------------------------------------
@app.route("/")
def index():
    """الصفحة الوحيدة — تُمرَّر البيانات المرجعية كـ JSON مضمّن."""
    groups_fields = {}
    for g, names in GROUPS.items():
        groups_fields[g] = [{
            "name": f["name"], "label_ar": f["label_ar"], "label_en": f["label_en"],
            "type": f["type"], "group": f["group"], "required": f["required"],
            "help": f["help_ar"], "ref": f["ref"], "max_len": f["max_len"],
            "pattern": f["pattern"], "options": bool(f["options"]),
        } for n in names if (f := FIELDS[n])]

    options = {n: [{"key": k, "ar": a, "en": e} for k, (a, e) in f["options"].items()]
               for n, f in FIELDS.items() if f["options"]}

    dict_json = json.dumps({
        "groups_fields": groups_fields,
        "options": options,
        "ref": reference.stats(),
        "required": [n for n in dic.REQUIRED_FIELDS],
        "excel_columns": dic.EXCEL_COLUMNS,
    }, ensure_ascii=False)

    return render_template(
        "index.html",
        dict_json=dict_json,
        rules_json=json.dumps(quality.RULE_CATALOGUE, ensure_ascii=False),
        engine_json=json.dumps(ocr.engine_status(), ensure_ascii=False),
        groups=[(g, [FIELDS[n] for n in names]) for g, names in GROUPS.items()],
        fields=DATA_DICTIONARY,
        engine_status=ocr.engine_status(),
        ref_stats=reference.stats(),
        version="1.0.0",
    )


# --------------------------------------------------------------------------
# API — لوحة المعلومات والبحث
# --------------------------------------------------------------------------
@app.route("/api/dashboard")
def api_dashboard():
    return _jresp(**pipeline.dashboard())


@app.route("/api/cases")
def api_cases():
    q = request.args.get("q", "")
    filters = {k: request.args.get(k, "") for k in
               ("district", "year", "site_prefix", "sex", "status")}
    return _jresp(cases=storage.search(q, **filters))


@app.route("/api/case/<path:registry_no>")
def api_case(registry_no):
    doc = storage.load_case(registry_no)
    if not doc:
        abort(404)
    return _jresp(
        registry_no=registry_no,
        fields=_case_payload(doc),
        record=_ordered_record(doc.get("case", {})),
        treatments=doc.get("treatments", []),
        documents=doc.get("documents", []),
        qc=doc.get("qc", {}),
        extraction=doc.get("extraction", {}),
        archive_path=storage.archive_url(registry_no),
        audit=storage.audit_trail(registry_no, limit=60),
    )


@app.route("/api/new")
def api_new():
    """سجل فارغ مع رقم تسلسلى محجوز."""
    return _jresp(
        registry_no=storage.next_registry_no(),
        fields=_case_payload({"case": {}}),
        record={}, treatments=[], documents=[], qc={}, extraction={},
        archive_path=str(storage.BASE_DIR / "documents"),
        audit=[],
    )


@app.route("/api/dictionary")
def api_dictionary():
    return _jresp(groups=[(g, [FIELDS[n]["name"] for n in names]) for g, names in GROUPS.items()],
                  fields=[{k: v for k, v in f.items() if k != "options"} for f in DATA_DICTIONARY],
                  options={n: [{"key": k, "ar": a, "en": e} for k, (a, e) in f["options"].items()]
                           for n, f in FIELDS.items() if f["options"]})


@app.route("/api/lookup/<kind>")
def api_lookup(kind):
    """بحث سريع فى جداول ICD-O-3 (يُستخدم في الإكمال التلقائي)."""
    q = (request.args.get("q") or "").strip().lower()
    if kind == "site":
        rows = [{"code": c, "ar": r.get("label_ar"), "en": r.get("label_en"),
                 "system": r.get("system")}
                for c, r in reference.topography().items()]
    elif kind == "morphology":
        rows = [{"code": c, "ar": r.get("label_ar"), "en": r.get("label_en"),
                 "behaviour": r.get("behaviour")}
                for c, r in reference.morphology().items()]
    else:
        abort(404)
    if q:
        rows = [r for r in rows
                if q in r["code"].lower() or q in (r["ar"] or "").lower()
                or q in (r["en"] or "").lower()]
    return _jresp(count=len(rows), rows=rows[:400])


@app.route("/api/audit")
def api_audit():
    no = request.args.get("registry_no", "")
    return _jresp(entries=storage.audit_trail(no, limit=300))


# --------------------------------------------------------------------------
# API — رفع واستخراج
# --------------------------------------------------------------------------
@app.route("/api/upload", methods=["POST"])
def api_upload():
    """
    يرفع ملفاً (أو عدة ملفات) ويشغّل خط المعالجة كاملاً.
    FormData: file(s) | registry_no | prefer | lang | manual_text
    """
    files = request.files.getlist("file")
    if not files or not any(f.filename for f in files):
        return _jresp(error="لم يُرفق أى ملف"), 400

    prefer = request.form.get("prefer", "auto")
    lang = request.form.get("lang", "ara+eng")
    registry_no = request.form.get("registry_no") or ""
    manual_text = request.form.get("manual_text") or ""

    results, errors = [], []
    for f in files:
        if not f.filename:
            continue
        suffix = Path(f.filename).suffix.lower()
        if suffix not in ocr.SUPPORTED_EXTS:
            errors.append({"file": f.filename,
                           "error": f"صيغة غير مدعومة ({suffix}) — المدعوم: "
                                    + "، ".join(sorted(ocr.SUPPORTED_EXTS))})
            continue
        tmp = UPLOAD_TMP / f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{Path(f.filename).name}"
        f.save(str(tmp))
        try:
            r = pipeline.process_file(tmp, registry_no=registry_no, prefer=prefer,
                                      lang=lang, manual_text=manual_text,
                                      save=not bool(registry_no))
            results.append(r)
            registry_no = r["registry_no"]       # الملفات التالية تُلحق بنفس السجل
        except Exception as exc:
            traceback.print_exc()
            errors.append({"file": f.filename, "error": str(exc)})

    if not results:
        return _jresp(errors=errors), 400

    main = results[0]
    doc = storage.load_case(main["registry_no"]) or {"case": main["record"]}
    storage.audit("document.process", main["registry_no"],
                  details={"files": [r["file"] for r in results],
                           "engine": main["ocr"]["engine"],
                           "confidence": main["extraction"]["confidence"]})
    return _jresp(
        ok=True,
        registry_no=main["registry_no"],
        fields=_case_payload(doc),
        record=_ordered_record(main["record"]),
        hits=main["extraction"]["hits"],
        ocr=main["ocr"],
        extraction=main["extraction"],
        qc=main["qc"],
        documents=storage.list_documents(main["registry_no"]),
        archive_path=storage.archive_url(main["registry_no"]),
        all_results=[{"file": r["file"], "engine": r["ocr"]["engine"],
                      "confidence": r["extraction"]["confidence"],
                      "filled": r["extraction"]["filled"]} for r in results],
        errors=errors,
        document_count=len(storage.list_documents(main["registry_no"])),
    )


@app.route("/api/extract-text", methods=["POST"])
def api_extract_text():
    """استخراج من نص مُلصق يدوياً (عند تعذّر OCR)."""
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    if len(text.strip()) < 10:
        return _jresp(error="النص قصير جداً — الصق محتوى التقرير كاملاً"), 400

    ext = extractor.extract(text, engine="manual", ocr_confidence=0.0)
    record = dict(data.get("record") or {})
    record = extractor.merge(record, ext, overwrite=data.get("overwrite", False))
    rep = quality.check_case(record).to_dict()
    storage.audit("extraction.manual_text", record.get("registry_no", ""),
                  details={"chars": len(text), "filled": len(ext.values)})
    return _jresp(
        ok=True, record=_ordered_record(record), hits=ext.hits and
        {k: vars(v) for k, v in ext.hits.items()},
        extraction=ext.to_dict(), qc=rep,
        ocr={"engine": "manual", "text": text, "confidence": 0.0,
             "pages": 1, "language": "manual", "warnings": ext.warnings},
    )


@app.route("/api/qc", methods=["POST"])
def api_qc():
    """فحص جودة لسجل (محفوظ أو قيد التحرير)."""
    data = request.get_json(silent=True) or {}
    record = _ordered_record(data.get("record") or {})
    registry_no = data.get("registry_no") or record.get("registry_no") or ""
    if registry_no and not record:
        doc = storage.load_case(registry_no)
        record = _ordered_record(doc.get("case", {}))
    record["document_count"] = record.get("document_count") or \
        len(storage.list_documents(registry_no)) if registry_no else 0
    rep = quality.check_case(record,
                             duplicates=storage.duplicate_keys(exclude=registry_no))
    storage.audit("qc.run", registry_no,
                  details={"score": rep.score, "status": rep.status,
                           "errors": len(rep.errors), "warnings": len(rep.warnings)})
    return _jresp(ok=True, qc=rep.to_dict(), text=rep.to_text(), registry_no=registry_no)


@app.route("/api/save", methods=["POST"])
def api_save():
    """يحفظ السجل (إنشاء أو تحديث)."""
    data = request.get_json(silent=True) or {}
    record = _ordered_record(data.get("record") or {})
    registry_no = data.get("registry_no") or record.get("registry_no") or ""
    if registry_no:
        doc = storage.load_case(registry_no)
        merged = dict(doc.get("case", {}))
        merged.update({k: v for k, v in record.items() if v not in (None, "")})
        record = merged
        record["registry_no"] = registry_no
    else:
        record["registry_no"] = storage.next_registry_no()
        registry_no = record["registry_no"]

    # إعادة حساب الحقول المشتقة
    _recompute(record)
    rep = quality.check_case(record, duplicates=storage.duplicate_keys(exclude=registry_no))
    record["qc_status"], record["qc_score"] = rep.status, rep.score
    record["qc_issues"] = "\n".join(f"[{i.severity}] {i.code} {i.message}" for i in rep.issues)
    record.setdefault("data_entry_status", "review")

    docs = storage.list_documents(registry_no)
    record["document_count"] = len(docs)
    saved = storage.save_case(record, treatments=data.get("treatments") or [],
                              documents=docs, qc_report=rep.to_dict())
    return _jresp(ok=True, registry_no=registry_no, record=_ordered_record(saved),
                  qc=rep.to_dict(), text=rep.to_text(), documents=docs,
                  archive_path=storage.archive_url(registry_no))


def _recompute(rec: dict):
    """يعيد حساب الحقول المشتقة بعد التعديل اليدوى."""
    site = reference.normalise_site(str(rec.get("primary_site") or ""))
    if site:
        rec["primary_site"] = site
        rec["primary_site_label"] = reference.site_label(site, "ar")
        i10 = reference.icd10_from_icdo3(site)
        if i10:
            rec["icd10_code"] = i10
    morph = reference.normalise_morphology(str(rec.get("morphology") or ""))
    if morph:
        rec["morphology"] = morph
        rec["morphology_label"] = reference.morphology_label(morph, "ar")
        beh = reference.behaviour_from_morphology(morph)
        if beh:
            rec["behaviour"] = beh
    if not rec.get("full_name"):
        parts = [rec.get(k, "") for k in ("first_name", "father_name",
                                          "grandfather_name", "family_name")]
        rec["full_name"] = " ".join(p for p in parts if p).strip()
    dob = extractor.parse_date(rec.get("birth_date"))
    dod = extractor.parse_date(rec.get("date_of_diagnosis"))
    if dob and dod:
        rec["age_at_diagnosis"] = dod.year - dob.year - ((dod.month, dod.day) < (dob.month, dob.day))
    if dod:
        rec["diagnosis_year"] = dod.year
    t = rec.get("pt") or rec.get("ct") or ""
    n = rec.get("pn") or rec.get("cn") or ""
    m = rec.get("pm") or rec.get("cm") or ""
    if t or n or m:
        sg = reference.derive_stage_group(site, t, n, m)
        if sg and not rec.get("pathological_stage"):
            rec["pathological_stage"] = sg
        ss = reference.summary_stage_from_tnm(t, n, m)
        if ss and ss != "unknown":
            rec["summary_stage"] = ss
    end = extractor.parse_date(rec.get("date_of_death")) or \
        extractor.parse_date(rec.get("last_followup_date"))
    if dod and end and end >= dod:
        rec["survival_months"] = (end.year - dod.year) * 12 + (end.month - dod.month)
    return rec


@app.route("/api/delete/<path:registry_no>", methods=["POST"])
def api_delete(registry_no):
    ok = storage.delete_case(registry_no)
    return _jresp(ok=ok, registry_no=registry_no)


@app.route("/api/status", methods=["POST"])
def api_status():
    """تغيير حالة السجل (اعتماد / مراجعة / تصدير)."""
    data = request.get_json(silent=True) or {}
    registry_no = data.get("registry_no")
    new = data.get("status")
    if not registry_no or new not in dic.DATA_ENTRY_STATUS:
        return _jresp(error="بيانات غير صالحة"), 400
    doc = storage.load_case(registry_no)
    if not doc:
        abort(404)
    rec = dict(doc["case"])
    rec["data_entry_status"] = new
    if new == "validated":
        rec["validated_by"] = data.get("user", "registry_officer")
        rec["validated_on"] = date.today().isoformat()
    storage.save_case(rec, treatments=doc.get("treatments"),
                      documents=doc.get("documents"), qc_report=doc.get("qc"),
                      extraction=doc.get("extraction"))
    storage.audit("case.status", registry_no, details={"status": new})
    return _jresp(ok=True, registry_no=registry_no, status=new)


# --------------------------------------------------------------------------
# API — التصدير والمستندات
# --------------------------------------------------------------------------
@app.route("/api/export")
def api_export():
    """تصدير كل السجلات إلى Excel."""
    only_validated = request.args.get("only_validated") == "1"
    try:
        path = pipeline.export_all(only_validated=only_validated, meta={
            "facility": request.args.get("facility", "مكتب سجل السرطان"),
            "author": request.args.get("author", "Cancer Registry Office"),
        })
    except ValueError as exc:
        return _jresp(error=str(exc)), 400
    return send_file(path, as_attachment=True, download_name=Path(path).name,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/api/export/<path:registry_no>")
def api_export_one(registry_no):
    try:
        path = pipeline.export_case(registry_no)
    except ValueError as exc:
        return _jresp(error=str(exc)), 404
    return send_file(path, as_attachment=True, download_name=Path(path).name,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/api/export/qc-report")
def api_export_qc():
    """تقرير جودة الدفعة الحالية كملف Excel مستقل."""
    from crcore import excel_export
    cases = storage.all_cases()
    records = [_ordered_record(c["case"]) for c in cases]
    if not records:
        return _jresp(error="لا توجد سجلات"), 400
    path = Path(storage.export_dir()) / f"QC_Report_{datetime.now():%Y%m%d_%H%M}.xlsx"
    excel_export.export_records(records, path, include_dictionary=False, include_refdata=False)
    return send_file(path, as_attachment=True, download_name=path.name,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/doc/<path:registry_no>/<path:filename>")
def serve_document(registry_no, filename):
    """يعرض الملف الأصلى داخل المتصفح (معاينة جنباً إلى جنب)."""
    for p in (storage.BASE_DIR / "documents").rglob("*"):
        if p.is_file() and p.parent.name == registry_no and p.name == filename:
            return send_file(str(p), mimetype=_mime(p.suffix.lower()),
                             conditional=True)
    abort(404)


def _mime(suffix):
    return {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg", ".tif": "image/tiff", ".tiff": "image/tiff",
            ".txt": "text/plain; charset=utf-8"}.get(suffix, "application/octet-stream")


@app.route("/api/documents/<path:registry_no>")
def api_documents(registry_no):
    docs = storage.list_documents(registry_no)
    for d in docs:
        p = Path(d["stored_path"])
        d["url"] = f"/doc/{registry_no}/{p.name}"
        d["exists"] = p.exists()
    return _jresp(documents=docs, archive_path=storage.archive_url(registry_no))


@app.route("/api/storage-info")
def api_storage_info():
    base = storage.BASE_DIR
    return _jresp(
        base_dir=str(base),
        cases_dir=str(base / "cases"),
        documents_dir=str(base / "documents"),
        exports_dir=str(base / "exports"),
        audit_log=str(base / "audit.jsonl"),
        engines=ocr.engine_status(),
        disk_free_gb=round(_disk_free(base) / 1e9, 2),
    )


def _disk_free(path):
    try:
        return os.statvfs(path).f_bavail * os.statvfs(path).f_frsize
    except (OSError, AttributeError):
        return 0


@app.errorhandler(Exception)
def _on_error(exc):
    if hasattr(exc, "code") and getattr(exc, "code", 500) < 500:
        return exc
    traceback.print_exc()
    return _jresp(error=str(exc), trace=traceback.format_exc(limit=6)), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8765))
    app.run(host=os.getenv("HOST", "0.0.0.0"), port=port, debug=False, threaded=True)

# -*- coding: utf-8 -*-
"""
مسارات HTTP الخاصة بالوحدة
===========================
1) ``/cancer_registry/doc/<id>/content``   — بث المستند داخل iframe (المعاينة جنباً إلى جنب)
2) ``/cancer_registry/storage/<case_id>``  — صفحة «مكان الملف المخزن» (DMS + المسار على القرص)
3) ``/cancer_registry/summary/<case_id>``  — ملخص قابل للطباعة
4) ``/cancer_registry/status``             — حالة محركات القراءة (Tesseract / poppler)
"""

import base64
import mimetypes
import os

from odoo import http, _
from odoo.http import request

from ..models import cr_bridge
ocr = cr_bridge.ocr
storage = cr_bridge.storage
dictionary = cr_bridge.dictionary
reference = cr_bridge.reference
quality = cr_bridge.quality

PAGE_CSS = """
* { box-sizing: border-box }
body { margin:0; background:#f2f5f9; color:#1c2b3a; direction:rtl; text-align:right;
       font-family:"Segoe UI",Tahoma,"Noto Sans Arabic",system-ui,sans-serif; font-size:14px }
.wrap { max-width:1080px; margin:0 auto; padding:22px 18px 60px }
h1 { font-size:20px; margin:0 0 4px }
.sub { color:#6b7a8d; font-size:12.5px; margin-bottom:20px }
.card { background:#fff; border:1px solid #e2e8f0; border-radius:10px;
        padding:16px 18px; margin-bottom:16px; box-shadow:0 1px 2px rgba(20,40,70,.04) }
.card h2 { font-size:15px; margin:0 0 12px; color:#123a63;
           border-bottom:2px solid #eaf1f9; padding-bottom:8px }
table { width:100%; border-collapse:collapse }
th, td { padding:7px 9px; border-bottom:1px solid #eef2f7; text-align:right;
         font-size:13px; vertical-align:top }
th { background:#f7fafd; color:#4a5b70; font-weight:600; font-size:12px }
code, .mono { font-family:"Consolas","Courier New",monospace; direction:ltr;
              unicode-bidi:embed; background:#f4f7fb; padding:1px 6px; border-radius:4px;
              font-size:12.5px; word-break:break-all }
.ok { color:#1a7f4b; font-weight:600 }
.warn { color:#a86a12; font-weight:600 }
.err { color:#b3261e; font-weight:600 }
.muted { color:#7b8798 }
.pill { display:inline-block; padding:2px 10px; border-radius:999px; font-size:11.5px;
        font-weight:600; background:#eaf1f9; color:#123a63 }
.toolbar { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:18px }
.btn { background:#123a63; color:#fff; border:0; border-radius:7px; padding:9px 16px;
       font-size:13px; font-weight:600; cursor:pointer; text-decoration:none }
.btn.ghost { background:#fff; color:#123a63; border:1px solid #c3d2e4 }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); gap:10px }
.tree { font-family:"Consolas","Courier New",monospace; direction:ltr; text-align:left;
        white-space:pre; background:#0f2033; color:#cfe3f7; padding:14px; border-radius:8px;
        font-size:12px; overflow:auto; line-height:1.65 }
@media print { .toolbar, .noprint { display:none } body { background:#fff }
               .card { box-shadow:none; break-inside:avoid } }
"""


def _page(title, subtitle, body, toolbar=""):
    return (
        '<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>%s</title><style>%s</style></head><body><div class="wrap">'
        '<h1>%s</h1><div class="sub">%s</div>%s%s</div></body></html>'
        % (title, PAGE_CSS, title, subtitle, toolbar, body))


def _esc(value):
    return (str(value if value is not None else "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def _human_size(n):
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "—"
    for unit in ("بايت", "ك.ب", "م.ب", "ج.ب"):
        if n < 1024 or unit == "ج.ب":
            return ("%.0f %s" % (n, unit)) if unit == "بايت" else ("%.1f %s" % (n, unit))
        n /= 1024.0
    return "—"


class CancerRegistryController(http.Controller):

    # =====================================================================
    #  1) بث المستند — للمعاينة داخل iframe
    # =====================================================================
    @http.route("/cancer_registry/doc/<int:doc_id>/content",
                type="http", auth="user", methods=["GET"])
    def document_content(self, doc_id, download=None, **kwargs):
        doc = request.env["cancer.registry.document"].browse(doc_id).exists()
        if not doc or not doc.file_content:
            return request.not_found()
        # تحقق من الصلاحية (يعمل على أودو 17 و 18 معاً)
        from odoo.exceptions import AccessError
        if not request.env.user.has_group("cancer_registry.group_registry_manager"):
            try:
                doc.case_id.read(["registry_no"])
            except AccessError:
                return request.not_found()

        payload = base64.b64decode(doc.file_content)
        suffix = os.path.splitext(doc.name or "")[1].lower()
        mime = {
            ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
            ".bmp": "image/bmp", ".tif": "image/tiff", ".tiff": "image/tiff",
            ".txt": "text/plain; charset=utf-8",
        }.get(suffix) or mimetypes.guess_type(doc.name or "")[0] \
            or "application/octet-stream"

        disposition = "attachment" if download else "inline"
        headers = [
            ("Content-Type", mime),
            ("Content-Length", str(len(payload))),
            ("Content-Disposition",
             '%s; filename="%s"' % (disposition, _esc(doc.name or "document"))),
            ("Cache-Control", "private, max-age=3600"),
            ("X-Frame-Options", "SAMEORIGIN"),
        ]
        return request.make_response(payload, headers=headers)

    # =====================================================================
    #  2) مكان الملف المخزن
    # =====================================================================
    @http.route("/cancer_registry/storage/<int:case_id>",
                type="http", auth="user", methods=["GET"])
    def storage_location(self, case_id, **kwargs):
        case = request.env["cancer.registry.case"].browse(case_id).exists()
        if not case:
            return request.not_found()

        info = storage.stats()
        base = storage.BASE_DIR
        docs = case.document_ids.sorted("uploaded_on", reverse=True)
        total_bytes = _dir_bytes(base)

        # جدول المرفقات
        rows = []
        for d in docs:
            rows.append(
                "<tr>"
                "<td>%s</td>"
                "<td>%s</td>"
                "<td class='muted'>%s</td>"
                "<td><code>%s</code></td>"
                "<td class='mono muted'>%s</td>"
                "<td><a class='btn ghost' style='padding:4px 10px' "
                "href='/cancer_registry/doc/%d/content?download=true'>تنزيل</a></td>"
                "</tr>" % (
                    _esc(d.name or "—"),
                    _esc(dict(d._fields["doc_type"].selection(d)).get(d.doc_type, "—")),
                    _human_size(d.file_size),
                    _esc(d.storage_path or _("غير مؤرشف على القرص")),
                    _esc((d.sha256 or "")[:16] + ("…" if d.sha256 else "")),
                    d.id))
        docs_table = (
            "<div class='card'><h2>مرفقات السجل (%s)</h2>"
            "<table><thead><tr><th>الملف</th><th>النوع</th><th>الحجم</th>"
            "<th>مسار الأرشيف</th><th>SHA-256</th><th></th></tr></thead>"
            "<tbody>%s</tbody></table></div>"
            % (len(docs), "".join(rows) or
               "<tr><td colspan='6' class='muted'>لا توجد مرفقات.</td></tr>"))

        # شجرة الأرشيف على القرص
        tree = _dir_tree(base, depth=3, max_entries=140)

        # وحدة Documents (Enterprise) إن كانت مثبّتة
        dms_block = ""
        if request.env["ir.model"].search([("model", "=", "documents.document")], limit=1):
            dms_docs = request.env["documents.document"].sudo().search(
                [("res_model", "=", case._name), ("res_id", "=", case.id)])
            dms_block = (
                "<div class='card'><h2>نظام إدارة المستندات (DMS)</h2>"
                "<p>عدد المستندات المفهرسة في DMS لهذه الحالة: <b>%s</b></p>"
                "<p class='muted'>افتحها من: المستندات ← مجلد «أرشيف سجل السرطان» "
                "← تصفية على هذه الحالة.</p></div>" % len(dms_docs))
        else:
            dms_block = (
                "<div class='card'><h2>نظام إدارة المستندات (DMS)</h2>"
                "<p class='muted'>وحدة <code>documents</code> (Odoo Enterprise) غير "
                "مثبّتة. تُستخدم المرفقات القياسية <code>ir.attachment</code> مع "
                "أرشفة مطابقة على القرص في المجلد أدناه — وهي كافية تماماً للعمل.</p></div>")

        toolbar = (
            "<div class='toolbar noprint'>"
            "<a class='btn ghost' href='/cancer_registry/storage'>كل الأرشيف</a>"
            "<a class='btn ghost' href='/web#id=%d&model=cancer.registry.case"
            "&view_type=form'>العودة إلى السجل</a>"
            "<button class='btn' onclick='window.print()'>طباعة</button>"
            "</div>" % case.id)

        body = (
            "<div class='card'><h2>ملخص التخزين</h2><table><tbody>"
            "<tr><th>جذر التخزين</th><td><code>%s</code></td></tr>"
            "<tr><th>عدد السجلات المؤرشفة</th><td><b>%s</b></td></tr>"
            "<tr><th>عدد المستندات المؤرشفة</th><td><b>%s</b></td></tr>"
            "<tr><th>الحجم الكلي</th><td><b>%s</b></td></tr>"
            "<tr><th>متوسط درجة الجودة</th><td><b>%s</b></td></tr>"
            "<tr><th>سجل التدقيق</th><td><code>%s</code></td></tr>"
            "<tr><th>الفهرس</th><td><code>%s</code></td></tr>"
            "</tbody></table></div>"
            % (_esc(base), _esc(info.get("total_cases", 0)),
               _esc(info.get("total_documents", 0)), _human_size(total_bytes),
               _esc("%.1f/100" % (info.get("avg_qc_score") or 0)),
               _esc(base / "audit.jsonl"), _esc(base / "index.json"))
            + dms_block + docs_table +
            "<div class='card'><h2>شجرة مجلد الأرشيف</h2>"
            "<div class='tree'>%s</div>"
            "<p class='muted' style='font-size:12px'>البنية: "
            "<code>documents/&lt;سنة التشخيص&gt;/&lt;رقم السجل&gt;/&lt;بصمة&gt;_&lt;الاسم&gt;</code> "
            "— البصمة تمنع تخزين نفس الملف مرتين.</p></div>" % _esc(tree))

        return request.make_response(
            _page(_("مكان الملف المخزن — %s") % case.registry_no,
                  _("أرشيف مستندات الحالة ومساراتها الفعلية على القرص وفي DMS"),
                  body, toolbar),
            headers=[("Content-Type", "text/html; charset=utf-8")])

    @http.route("/cancer_registry/storage", type="http", auth="user", methods=["GET"])
    def storage_root(self, **kwargs):
        info = storage.stats()
        base = storage.BASE_DIR
        cases = storage.all_cases()[-40:][::-1]
        rows = "".join(
            "<tr><td><code>%s</code></td><td>%s</td><td>%s</td><td>%s</td>"
            "<td><span class='pill'>%s</span></td></tr>" % (
                _esc(c["case"].get("registry_no")), _esc(c["case"].get("full_name")),
                _esc(c["case"].get("primary_site")), _esc(c["case"].get("date_of_diagnosis")),
                _esc(c["case"].get("qc_status")))
            for c in cases)
        body = (
            "<div class='card'><h2>جذر التخزين</h2><p><code>%s</code></p>"
            "<p class='muted'>غيّره بمتغيّر البيئة <code>CR_STORAGE_DIR</code> "
            "أو <code>data_dir</code> في إعدادات أودو.</p></div>"
            "<div class='card'><h2>الإحصاءات</h2><table><tbody>"
            "<tr><th>السجلات</th><td>%s</td></tr>"
            "<tr><th>المستندات</th><td>%s</td></tr>"
            "<tr><th>الحجم</th><td>%s</td></tr>"
            "<tr><th>متوسط الجودة</th><td>%s</td></tr>"
            "</tbody></table></div>"
            "<div class='card'><h2>توزيع الحالات المؤرشفة</h2>"
            "<div class='grid'>" + _dist_block(_("حسب الموقع الأولي"), info.get("by_site"))
            + _dist_block(_("حسب البلدية"), info.get("by_district"))
            + _dist_block(_("حسب الجنس"), info.get("by_sex"))
            + _dist_block(_("حسب سنة التشخيص"), info.get("by_year"))
            + _dist_block(_("حسب حالة الجودة"), info.get("by_qc_status"))
            + "</div></div>"
            "<div class='card'><h2>آخر %s سجل</h2>"
            "<table><thead><tr><th>الرقم</th><th>الاسم</th><th>الموقع</th>"
            "<th>التشخيص</th><th>الجودة</th></tr></thead><tbody>%s</tbody></table></div>"
            "<div class='card'><h2>الشجرة</h2><div class='tree'>%s</div></div>"
            % (_esc(base), _esc(info.get("cases", 0)), _esc(info.get("documents", 0)),
               _human_size(_dir_bytes(base)),
               _esc("%.1f/100" % (info.get("avg_qc_score") or 0)), len(cases),
               rows or "<tr><td colspan='5' class='muted'>فارغ</td></tr>",
               _esc(_dir_tree(base, depth=3, max_entries=200))))
        return request.make_response(
            _page(_("أرشيف سجل السرطان"), _("محتوى مجلد التخزين على القرص"), body),
            headers=[("Content-Type", "text/html; charset=utf-8")])

    # =====================================================================
    #  3) ملخص قابل للطباعة
    # =====================================================================
    @http.route("/cancer_registry/summary/<int:case_id>",
                type="http", auth="user", methods=["GET"])
    def summary(self, case_id, **kwargs):
        case = request.env["cancer.registry.case"].browse(case_id).exists()
        if not case:
            return request.not_found()
        record = case._as_record_dict()
        report = quality.check_case(record)

        rows = []
        for group, names in dictionary.GROUPS.items():
            rows.append("<tr><th colspan='3' style='background:#eaf1f9;color:#123a63'>"
                        "%s</th></tr>" % _esc(group))
            for n in names:
                fld = dictionary.FIELDS[n]
                if fld["type"] == "one2many":
                    continue
                value = record.get(n, "")
                if fld["type"] == "selection" and value:
                    value = dictionary.option_label(n, value) or value
                elif fld["type"] == "boolean":
                    value = _("نعم") if value else _("لا")
                if value in ("", None, False):
                    continue
                rows.append("<tr><td style='width:26%%;color:#5b6b7f'>%s</td>"
                            "<td style='width:26%%;color:#9aa7b6;font-size:11.5px'>%s</td>"
                            "<td><b>%s</b></td></tr>"
                            % (_esc(fld["label_ar"]), _esc(n), _esc(value)))

        issues = "".join(
            "<tr><td><code>%s</code></td><td class='%s'>%s</td><td>%s</td>"
            "<td>%s</td><td>%s</td></tr>" % (
                _esc(i.code), "err" if i.severity == "error" else "warn",
                _esc(_("خطأ") if i.severity == "error" else _("تحذير")),
                _esc(dictionary.label(i.field)),
                _esc(i.message), _esc(i.fix))
            for i in report.issues if i.severity != "info")

        toolbar = ("<div class='toolbar noprint'>"
                   "<button class='btn' onclick='window.print()'>طباعة الملخص</button>"
                   "<a class='btn ghost' href='/web#id=%d&model=cancer.registry.case"
                   "&view_type=form'>العودة إلى السجل</a></div>" % case.id)

        body = (
            "<div class='card'><h2>الجودة</h2><p>الدرجة: <b class='%s'>%s/100</b> "
            "&nbsp; <span class='pill'>%s</span> &nbsp; %s خطأ، %s تحذير</p></div>"
            "<div class='card'><h2>الملخص التفصيلي</h2>"
            "<table><tbody>%s</tbody></table></div>"
            "<div class='card'><h2>ملاحظات فحص الجودة</h2>"
            "<table><thead><tr><th>القاعدة</th><th>الخطورة</th><th>الحقل</th>"
            "<th>المشكلة</th><th>الإصلاح</th></tr></thead>"
            "<tbody>%s</tbody></table></div>"
            % ("err" if report.status == "error" else
               ("warn" if report.status == "warning" else "ok"),
               report.score, _esc(dictionary.option_label("qc_status", report.status)),
               len(report.errors), len(report.warnings),
               "".join(rows),
               issues or "<tr><td colspan='5' class='ok'>لا توجد مشاكل. ✓</td></tr>"))
        return request.make_response(
            _page(_("ملخص الحالة %s") % case.registry_no,
                  _esc(case.full_name or "") + " — " +
                  _("المعهد القومي للأورام، صبراتة"), body, toolbar),
            headers=[("Content-Type", "text/html; charset=utf-8")])

    # =====================================================================
    #  4) حالة محركات القراءة
    # =====================================================================
    @http.route("/cancer_registry/status", type="http", auth="user", methods=["GET"])
    @http.route("/cancer_registry/status.json", type="json", auth="user",
                methods=["POST"])
    def engine_status(self, **kwargs):
        status = ocr.engine_status()
        status["reference"] = reference.stats()
        status["dictionary"] = {
            "fields": len(dictionary.FIELDS),
            "groups": len(dictionary.GROUPS),
            "required": len(dictionary.REQUIRED_FIELDS),
            "excel_columns": len(dictionary.EXCEL_COLUMNS),
        }
        _DIC_LABELS = {
            "fields": _("عدد الحقول في القاموس"),
            "groups": _("عدد المجموعات (A–G)"),
            "required": _("عدد الحقول الإلزامية"),
            "excel_columns": _("عدد أعمدة ملف التصدير"),
        }
        status["quality_rules"] = len(quality.RULE_CATALOGUE)
        if request.httprequest.path.endswith(".json"):
            return status

        langs = status.get("tesseract_languages") or []
        engines = "".join(
            "<tr><td><b>%s</b></td><td class='%s'>%s</td><td class='muted'>%s</td></tr>" % (
                _esc(label),
                "ok" if ok else "err",
                _esc(_("متاح") if ok else _("غير متاح")),
                _esc(detail))
            for label, ok, detail in _ENGINE_ROWS(status, langs))
        refs = "".join("<tr><td>%s</td><td><b>%s</b></td></tr>"
                       % (_esc(_REF_LABELS.get(k, k)), _esc(v))
                       for k, v in status["reference"].items())
        dic = "".join("<tr><td>%s</td><td><b>%s</b></td></tr>"
                      % (_esc(_DIC_LABELS.get(k, k)), _esc(v))
                      for k, v in status["dictionary"].items())
        body = (
            "<div class='card'><h2>محركات قراءة المستندات</h2>"
            "<table><thead><tr><th>المحرك</th><th>الحالة</th>"
            "<th>التفاصيل</th></tr></thead><tbody>%s</tbody></table>"
            "<p class='muted' style='font-size:12.5px;margin-top:10px'>"
            "بدون Tesseract تعمل الوحدة على ملفات PDF النصية والملفات النصية "
            "والإدخال اليدوي بشكل كامل. لتفعيل قراءة الصور الممسوحة ضوئياً "
            "ثبّت <code>tesseract-ocr</code> و<code>tesseract-ocr-ara</code> "
            "على خادم أودو ثم أعد تشغيل الخدمة.</p></div>"
            "<div class='card'><h2>البيانات المرجعية</h2>"
            "<table><tbody>%s</tbody></table></div>"
            "<div class='card'><h2>قاموس الحقول</h2>"
            "<table><tbody>%s</tbody></table>"
            "<p class='muted'>قواعد الجودة: <b>%s</b></p></div>"
            "<div class='card'><h2>ملاحظة المحرك</h2><p>%s</p></div>"
            % (engines or "<tr><td colspan='3' class='muted'>—</td></tr>",
               refs, dic, status["quality_rules"], _esc(status.get("note", ""))))
        return request.make_response(
            _page(_("حالة النظام"), _("محركات القراءة والبيانات المرجعية"), body),
            headers=[("Content-Type", "text/html; charset=utf-8")])


_REF_LABELS = {
    "topography_codes": _("رموز ICD-O-3 للمواقع (Topography)"),
    "morphology_codes": _("رموز ICD-O-3 للفحص النسيجي (Morphology)"),
    "tnm_rules": _("قواعد اشتقاق مرحلة TNM"),
    "icd10_codes": _("رموز ICD-10 للأورام (C00–D49)"),
}


def _ENGINE_ROWS(status, langs):
    """[(الاسم، متاح؟، التفاصيل)] من ناتج ocr.engine_status()."""
    arabic = "ara" in (langs or []) or "ara+eng" in (langs or [])
    return [
        (_("Tesseract OCR (الصور الممسوحة)"), bool(status.get("tesseract")),
         _("اللغات المثبّتة: %s") % (", ".join(langs) if langs else _("لا شىء"))
         if status.get("tesseract") else
         _("ثبّته من UB-Mannheim على Windows أو apt على Debian/Ubuntu")),
        (_("دعم اللغة العربية في Tesseract"), arabic,
         _("الحزمة المطلوبة: tesseract-ocr-ara") if not arabic else _("متاحة")),
        (_("pdftoppm — تحويل PDF إلى صور"), bool(status.get("pdftoppm")),
         _("الحزمة المطلوبة: poppler-utils") if not status.get("pdftoppm")
         else _("متاح")),
        (_("pypdf — نص PDF المدمج"), bool(status.get("pypdf")), _("")),
        (_("pdfminer.six — بديل قراءة PDF"), bool(status.get("pdfminer")), _("")),
        (_("Azure AI Document Intelligence"), bool(status.get("azure_di")),
         _("فعّله بمتغيرات البيئة AZURE_DI_ENDPOINT / AZURE_DI_KEY")
         if not status.get("azure_di") else _("مُهيَّأ")),
        (_("محرك OpenAI / LLM"), bool(status.get("openai")),
         _("فعّله بمتغير البيئة OPENAI_API_KEY")
         if not status.get("openai") else _("مُهيَّأ")),
    ]


def _dist_block(title, mapping):
    if not mapping:
        return ""
    rows = "".join("<tr><td>%s</td><td style='text-align:left'><b>%s</b></td></tr>"
                   % (_esc(k), _esc(v)) for k, v in sorted(
                       mapping.items(), key=lambda kv: -kv[1]))
    return ("<div style='background:#fff;border:1px solid #e2e8f0;border-radius:8px;"
            "padding:10px 12px'><div style='font-weight:600;font-size:13px;"
            "color:#123a63;margin-bottom:6px'>%s</div>"
            "<table style='font-size:12.5px'>%s</table></div>" % (_esc(title), rows))


def _dir_bytes(root):
    total = 0
    root = str(root)
    if not os.path.isdir(root):
        return 0
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                pass
    return total


def _dir_tree(root, depth=3, max_entries=150):
    """شجرة نصية بسيطة لمجلد الأرشيف."""
    root = str(root)
    if not os.path.isdir(root):
        return "(مجلد التخزين غير موجود بعد)"
    lines = [root + "/"]
    count = [0]

    def walk(path, prefix, level):
        if level > depth or count[0] >= max_entries:
            return
        try:
            entries = sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name))
        except OSError:
            return
        entries = [e for e in entries if e.name not in ("__pycache__", ".git")]
        for i, entry in enumerate(entries):
            if count[0] >= max_entries:
                lines.append(prefix + "… (تم الاقتصار على %d عنصراً)" % max_entries)
                return
            last = (i == len(entries) - 1)
            branch = "└── " if last else "├── "
            if entry.is_dir():
                n = sum(1 for _ in os.scandir(entry.path))
                lines.append("%s%s%s/  (%d)" % (prefix, branch, entry.name, n))
                count[0] += 1
                walk(entry.path, prefix + ("    " if last else "│   "), level + 1)
            else:
                try:
                    size = _human_size(entry.stat().st_size)
                except OSError:
                    size = "?"
                lines.append("%s%s%s  [%s]" % (prefix, branch, entry.name, size))
                count[0] += 1

    walk(root, "", 1)
    return "\n".join(lines)

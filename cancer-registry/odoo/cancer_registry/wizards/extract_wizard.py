# -*- coding: utf-8 -*-
"""
معالج «لصق النص يدوياً»
========================
يُستخدم عندما:
  * المستند صورة رديئة المسح ولا يقرأها OCR بدقة، فينسخ المستخدم النص من
    أي مصدر (تقرير إلكتروني، بريد، ملف Word) ويلصقه هنا؛
  * أو عندما يصل التبليغ كنص عادي من المستشفى المبلِّغ.

خطوتان: استخراج (معاينة) ثم تفريغ في السجل — لا كتابة عمياء.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..models import cr_bridge
dictionary = cr_bridge.dictionary
extractor = cr_bridge.extractor
reference = cr_bridge.reference

LANGS = [
    ("ara+eng", "عربي + إنجليزي (موصى به)"),
    ("ara", "عربي فقط"),
    ("eng", "إنجليزي فقط"),
]

ENGINE_PREFS = [
    ("auto", "تلقائي"),
    ("manual", "نص ملصوق يدوياً"),
    ("text-file", "ملف نصي"),
    ("pdf-embedded", "نص مدمج في PDF"),
    ("tesseract", "Tesseract OCR"),
    ("azure-di", "Azure AI Document Intelligence"),
]


class CancerRegistryExtractWizard(models.TransientModel):
    _name = "cancer.registry.extract.wizard"
    _description = "استخراج الحقول من نص ملصوق"

    case_id = fields.Many2one("cancer.registry.case", string="السجل",
                              required=True, ondelete="cascade")
    registry_no = fields.Char(related="case_id.registry_no", string="رقم السجل")
    raw_text = fields.Text(
        string="النص الخام",
        help="الصق هنا نص التقرير كما هو — لا حاجة لتنسيقه. "
             "المحرّك يبحث عن التسميات (الاسم، الرقم الوطني، الموقع الأولي، "
             "الفحص النسيجي، TNM، التاريخ، العلاج…) بالعربية والإنجليزية.")
    lang = fields.Selection(LANGS, string="لغة المستند", default="ara+eng")
    engine_pref = fields.Selection(ENGINE_PREFS, string="المحرك المفضّل",
                                   default="manual")
    overwrite = fields.Boolean(
        string="الكتابة فوق القيم الموجودة",
        default=False,
        help="بدون هذا الخيار تُملأ الحقول الفارغة فقط، ويُحفظ ما أدخله المستخدم يدوياً.")
    attach_to_document = fields.Boolean(
        string="حفظ النص كمستند في الأرشيف", default=True,
        help="ينشئ مستنداً من نوع «استمارة تبليغ» يحمل النص الملصوق كمرجع دائم.")

    # نتائج الخطوة الأولى
    result_json = fields.Text(string="النتيجة (JSON)", readonly=True)
    result_html = fields.Html(string="معاينة الحقول المستخرجة", sanitize=False,
                              readonly=True)
    fields_count = fields.Integer(string="عدد الحقول", readonly=True)
    confidence = fields.Float(string="الثقة %", digits=(5, 2), readonly=True)
    step = fields.Selection([("input", "إدخال النص"), ("review", "مراجعة")],
                            string="الخطوة", default="input")

    # ------------------------------------------------------------------
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx_case = self.env.context.get("default_case_id")
        if ctx_case and "case_id" not in res:
            res["case_id"] = ctx_case
        return res

    def action_extract(self):
        """الخطوة 1 — استخراج مع معاينة قبل أي كتابة."""
        self.ensure_one()
        text = (self.raw_text or "").strip()
        if len(text) < 20:
            raise UserError(_(
                "النص قصير جداً (%s حرفاً).\n"
                "الصق نص التقرير كاملاً — الاسم، الرقم الوطني، تاريخ التشخيص، "
                "الموقع الأولي، الفحص النسيجي، والمرحلة.") % len(text))

        res = extractor.extract(text, engine=self.engine_pref or "manual",
                                ocr_confidence=99.0 if self.engine_pref == "manual" else 0.0)
        record = res.values or {}
        filled = {k: v for k, v in record.items()
                  if v not in (None, "", [], False) and not k.startswith("_")}

        import json
        self.write({
            "result_json": json.dumps(res.to_dict(), ensure_ascii=False, default=str),
            "fields_count": len(filled),
            "confidence": res.overall_confidence or 0.0,
            "step": "review",
            "result_html": self._render_preview(filled, res.hits, record),
        })
        return self._reopen()

    def _render_preview(self, filled, hits, record):
        """جدول: الحقل ← القيمة المستخرجة ← الدليل من النص ← هل سيُكتب؟"""
        case = self.case_id
        rows = []
        for name in dictionary.EXCEL_COLUMNS:
            if name not in dictionary.FIELDS:
                continue
            fld = dictionary.FIELDS[name]
            if fld["type"] == "one2many" or name.startswith("_"):
                continue
            value = filled.get(name)
            if value is None:
                continue
            shown = value
            if fld["type"] == "selection":
                shown = dictionary.option_label(name, value) or value
            elif fld["type"] == "boolean":
                shown = _("نعم") if value else _("لا")

            current = case[name] if name in case._fields else False
            will_write = self.overwrite or current in (False, None, "", 0, 0.0)
            if not will_write:
                state = ("<span class='pill' style='background:#fdf1dc;color:#8a5a09'>"
                         "موجود — لن يُستبدل</span>")
            elif fld["required"]:
                state = ("<span class='pill' style='background:#e3f4e9;color:#1a7f4b'>"
                         "إلزامي ✓</span>")
            else:
                state = ("<span class='pill' style='background:#eaf1f9;color:#123a63'>"
                         "سيُكتب</span>")

            hit = hits.get(name)
            evidence = getattr(hit, "evidence", "") or getattr(hit, "value", "") or ""
            method = getattr(hit, "method", "") or ""
            hit_conf = getattr(hit, "confidence", 0) or 0
            rows.append(
                "<tr><td style='white-space:nowrap'><b>%s</b><br/>"
                "<span class='muted mono' style='font-size:11px'>%s</span></td>"
                "<td><b>%s</b></td>"
                "<td class='muted' style='font-size:12px;max-width:300px'>"
                "<span style='direction:ltr;unicode-bidi:embed'>«%s»</span><br/>"
                "<span style='font-size:11px'>%s — %s%%</span></td>"
                "<td>%s</td></tr>" % (
                    _esc(fld["label_ar"]), _esc(name), _esc(shown),
                    _esc(str(evidence)[:150]), _esc(str(method)),
                    "%.0f" % (hit_conf * 100), state))

        missing = [dictionary.label(n) for n in dictionary.REQUIRED_FIELDS
                   if not filled.get(n) and not (n in case._fields and case[n])]
        warn = ""
        if missing:
            warn = ("<div class='card' style='border-color:#f0c9c4;background:#fdf5f4'>"
                    "<h2 style='color:#b3261e;border-color:#f6dedb'>حقول إلزامية ناقصة</h2>"
                    "<p>%s</p></div>" % _esc("، ".join(missing)))

        return (
            _STYLE +
            "<div class='card'><h2>نتيجة الاستخراج</h2>"
            "<p>استُخرج <b>%s</b> حقل &nbsp;•&nbsp; الثقة <b>%s%%</b> "
            "&nbsp;•&nbsp; المحرك <code>%s</code></p></div>"
            "%s"
            "<div class='card'><h2>معاينة الحقول — راجعها قبل التفريغ</h2>"
            "<table><thead><tr><th>الحقل</th><th>القيمة المستخرجة</th>"
            "<th>الدليل من النص</th><th>الإجراء</th></tr></thead>"
            "<tbody>%s</tbody></table></div>"
            % (len(rows), "%.1f" % (self.confidence or 0),
               _esc(dict(self._fields["engine_pref"].selection(self))
                    .get(self.engine_pref, "")),
               warn, "".join(rows) or
               "<tr><td colspan='4' class='muted'>لم يُستخرج شىء.</td></tr>") + "</div>")

    def action_apply(self):
        """الخطوة 2 — التفريغ في السجل."""
        self.ensure_one()
        import json
        if not self.result_json:
            raise UserError(_("شغّل الاستخراج أولاً."))
        data = json.loads(self.result_json)
        record = data.get("values") or data.get("record") or {}
        case = self.case_id

        vals = {}
        for key, value in record.items():
            if key not in case._fields or key.startswith("_"):
                continue
            fld = case._fields[key]
            if fld.readonly or fld.related or fld.type in ("one2many", "many2many",
                                                          "binary"):
                continue
            current = case[key]
            if current not in (False, None, "", 0, 0.0) and not self.overwrite:
                continue
            try:
                if fld.type == "date":
                    value = fields.Date.to_date(str(value)[:10])
                elif fld.type == "datetime":
                    value = fields.Datetime.to_datetime(value)
                elif fld.type == "selection":
                    if value not in [k for k, _ in fld.selection(case)]:
                        continue
                elif fld.type == "integer":
                    value = int(value)
                elif fld.type == "float":
                    value = float(value)
                else:
                    value = str(value)[:fld.size] if fld.size else str(value)
            except (ValueError, TypeError):
                continue
            vals[key] = value

        vals["extraction_method"] = dict(self._fields["engine_pref"].selection(self)) \
            .get(self.engine_pref, "manual")
        vals["extraction_confidence"] = self.confidence or 0.0
        if vals.get("first_name") or vals.get("family_name"):
            vals.setdefault("data_entry_status", "extracted")

        if not vals:
            raise UserError(_("لا توجد حقول جديدة للتفريغ."))
        case.write(vals)
        case._recompute_derived()

        if self.attach_to_document and (self.raw_text or "").strip():
            import base64
            self.env["cancer.registry.document"].create({
                "case_id": case.id,
                "name": _("بلاغ نصي — %s.txt") % case.registry_no.replace("/", "-"),
                "file_content": base64.b64encode(
                    self.raw_text.strip().encode("utf-8")),
                "doc_type": "notification",
                "extracted_text": self.raw_text.strip()[:200000],
                "ocr_engine": "manual-paste",
                "ocr_confidence": 99.0,
                "extraction_done": True,
            })

        case.message_post(body=_(
            "تفريغ من نص ملصوق — %s حقل (ثقة %s%%)") % (len(vals), self.confidence or 0))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("تم التفريغ"),
                       "message": _("أُضيف/حُدِّث %s حقل في السجل %s.")
                                    % (len(vals), case.registry_no),
                       "type": "success", "sticky": False, "next": {
                           "type": "ir.actions.act_window_close"}},
        }

    def action_back(self):
        self.ensure_one()
        self.write({"step": "input"})
        return self._reopen()

    def action_load_document_text(self):
        """يجلب نص آخر مستند مرفق إلى مربع النص."""
        self.ensure_one()
        doc = self.case_id.document_ids.sorted("uploaded_on", reverse=True)[:1]
        if not doc:
            raise UserError(_("لا يوجد مستند مرفق بهذه الحالة."))
        if not doc.extracted_text:
            doc.run_extraction()
        self.write({"raw_text": doc.extracted_text or ""})
        return self._reopen()

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "context": self.env.context,
        }


_STYLE = """<style>
.cr-wiz * { box-sizing: border-box }
.cr-wiz { direction: rtl; text-align: right; font-size: 13px; color: #1c2b3a }
.cr-wiz .card { background:#fff; border:1px solid #e2e8f0; border-radius:10px;
                padding:12px 14px; margin-bottom:12px }
.cr-wiz .card h2 { font-size:14px; margin:0 0 8px; color:#123a63;
                   border-bottom:2px solid #eaf1f9; padding-bottom:6px }
.cr-wiz table { width:100%; border-collapse:collapse }
.cr-wiz th, .cr-wiz td { padding:6px 8px; border-bottom:1px solid #eef2f7;
                         text-align:right; vertical-align:top }
.cr-wiz th { background:#f7fafd; color:#4a5b70; font-weight:600; font-size:11.5px }
.cr-wiz .mono, .cr-wiz code { font-family:Consolas,"Courier New",monospace;
                              direction:ltr; unicode-bidi:embed }
.cr-wiz .muted { color:#7b8798 }
.cr-wiz .pill { display:inline-block; padding:2px 9px; border-radius:999px;
                font-size:11px; font-weight:600; background:#eaf1f9; color:#123a63 }
</style><div class="cr-wiz">"""


def _esc(value):
    return (str(value if value is not None else "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))

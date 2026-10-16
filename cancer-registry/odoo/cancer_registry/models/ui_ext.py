# -*- coding: utf-8 -*-
"""
امتدادات الواجهة — مكتوبة يدوياً
=================================
كل ما يخص **العرض** فقط: المعاينة جنباً إلى جنب، العدّادات للأزرار الذكية،
تزيين القوائم حسب حالة الجودة، وفتح مجلد الأرشيف.

الحقول الطبية نفسها كلها في ``models/cancer_registry.py`` (مُولَّد من القاموس) —
لا تضف حقلاً طبياً هنا أبداً؛ أضفه إلى ``crcore/dictionary.py`` ثم أعد التوليد.
"""

import base64
import os

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from . import cr_bridge
dictionary = cr_bridge.dictionary
reference = cr_bridge.reference
storage = cr_bridge.storage
pipeline = cr_bridge.pipeline
excel_export = cr_bridge.excel_export

QC_COLORS = {"not_run": 5, "pass": 10, "warning": 3, "error": 1}
QC_ICONS = {
    "not_run": "fa-circle-o text-muted",
    "pass": "fa-check-circle text-success",
    "warning": "fa-exclamation-triangle text-warning",
    "error": "fa-times-circle text-danger",
}


# ═══════════════════════════════════════════════════════════════════════════
#  الحالة
# ═══════════════════════════════════════════════════════════════════════════
class CancerRegistryCaseExt(models.Model):
    _inherit = "cancer.registry.case"

    # ------------------------------------------------------------------ عدّادات
    document_count = fields.Integer(
        string="عدد المستندات", compute="_compute_document_count", store=True,
        help="يُحسب تلقائياً من المرفقات — مطابق لحقل القاموس المستخدم في التصدير")
    nb_documents = fields.Integer(
        string="المستندات", compute="_compute_counters")
    nb_issues_open = fields.Integer(
        string="مشاكل مفتوحة", compute="_compute_counters")
    nb_errors = fields.Integer(string="أخطاء", compute="_compute_counters")
    nb_treatments = fields.Integer(
        string="سطور العلاج", compute="_compute_counters")

    # ------------------------------------------------------------------ زخرفة
    color = fields.Integer(string="لون البطاقة", default=0,
                           help="يُستخدم في لوحة الكانبان — لا معنى طبي له")
    qc_color = fields.Integer(
        string="لون الجودة", compute="_compute_qc_decoration",
        help="يُستخدم في تلوين شارة حالة الجودة داخل القائمة")
    qc_badge = fields.Char(string="شارة الجودة", compute="_compute_qc_decoration")
    data_entry_badge = fields.Char(
        string="شارة الإدخال", compute="_compute_qc_decoration")
    duplicate_warning = fields.Char(
        string="تنبيه تكرار", compute="_compute_duplicate_warning",
        search="_search_duplicate_warning",
        help="يظهر أعلى النموذج إن وُجد سجل آخر بنفس الرقم الوطني وتاريخ التشخيص")

    # ------------------------------------------------------------------ المعاينة
    first_document_id = fields.Many2one(
        "cancer.registry.document", string="المستند المعروض",
        compute="_compute_first_document", inverse="_set_first_document",
        store=False,
        help="اختر المستند الذي تريد عرضه في لوحة المعاينة اليمنى")
    preview_html = fields.Html(
        string="معاينة المستند", compute="_compute_preview_html",
        sanitize=False, readonly=True)
    extracted_text_preview = fields.Html(
        string="النص المستخرج", compute="_compute_extracted_text_preview",
        sanitize=False, readonly=True)
    summary_html = fields.Html(
        string="الملخص", compute="_compute_summary_html",
        sanitize=False, readonly=True)

    # ------------------------------------------------------------------ حسابات
    @api.depends("document_ids")
    def _compute_document_count(self):
        for rec in self:
            rec.document_count = len(rec.document_ids)

    @api.depends("document_ids", "qc_issue_ids", "qc_issue_ids.resolved",
                 "qc_issue_ids.severity", "treatment_ids")
    def _compute_counters(self):
        for rec in self:
            rec.nb_documents = len(rec.document_ids)
            rec.nb_treatments = len(rec.treatment_ids)
            open_issues = rec.qc_issue_ids.filtered(lambda i: not i.resolved)
            rec.nb_issues_open = len(open_issues)
            rec.nb_errors = len(open_issues.filtered(lambda i: i.severity == "error"))

    @api.depends("qc_status", "qc_score", "data_entry_status")
    def _compute_qc_decoration(self):
        for rec in self:
            rec.qc_color = QC_COLORS.get(rec.qc_status or "not_run", 5)
            rec.qc_badge = "%s %s/100" % (
                dictionary.option_label("qc_status", rec.qc_status or "not_run"),
                rec.qc_score or 0)
            rec.data_entry_badge = dictionary.option_label(
                "data_entry_status", rec.data_entry_status or "draft")

    @api.depends("national_id", "primary_site", "date_of_diagnosis")
    def _compute_duplicate_warning(self):
        for rec in self:
            rec.duplicate_warning = False
            if not (rec.national_id and rec.date_of_diagnosis):
                continue
            same = self.search([
                ("id", "!=", rec.id or 0),
                ("national_id", "=", rec.national_id),
                ("date_of_diagnosis", "=", rec.date_of_diagnosis),
            ], limit=2)
            if same:
                rec.duplicate_warning = _(
                    "⚠ توجد %s سجل(ات) أخرى بنفس الرقم الوطني وتاريخ التشخيص: %s") % (
                        len(same), "، ".join(same.mapped("registry_no")))

    def _search_duplicate_warning(self, operator, value):
        """يبحث عن السجلات التي لها نظير بنفس الرقم الوطني وتاريخ التشخيص.

        يستخدم read_group بدلاً من المرور على كل السجلات — تكلفة ثابتة.
        """
        negative = operator in ("!=", "not ilike", "not like", "not in")
        want = (not value) if negative else bool(value)
        if not want:
            return [("id", "=", 0)] if not negative else []

        grouped = self.with_context(active_test=False).read_group(
            [("national_id", "!=", False), ("date_of_diagnosis", "!=", False)],
            ["national_id"], ["national_id", "date_of_diagnosis"], lazy=False)
        pairs = [(g["national_id"], g["date_of_diagnosis"])
                 for g in grouped if g.get("__count", g.get("national_id_count", 0)) > 1]
        if not pairs:
            return [("id", "=", 0)] if want else []

        domain = ["|"] * (len(pairs) - 1)
        for nid, dod in pairs:
            domain += ["&", ("national_id", "=", nid), ("date_of_diagnosis", "=", dod)]
        if not want:
            domain = ["!"] + domain
        return domain

    @api.depends("document_ids", "document_ids.extracted_text",
                 "document_ids.file_content", "first_document_id")
    def _compute_first_document(self):
        for rec in self:
            if rec.first_document_id and rec.first_document_id in rec.document_ids:
                continue
            rec.first_document_id = rec.document_ids[:1] or False

    def _set_first_document(self):
        # حقل تخزينه معطّل — لا شىء يُكتب
        pass

    @api.depends("first_document_id", "first_document_id.file_content",
                 "first_document_id.extracted_text")
    def _compute_preview_html(self):
        for rec in self:
            doc = rec.first_document_id
            if not doc:
                rec.preview_html = _empty_panel(_(
                    "لا يوجد مستند مرفق.\nاستخدم زر «رفع مستند ممسوح ضوئياً / PDF» "
                    "في الأعلى لإرفاق التقرير الورقي بعد مسحه."))
                continue
            rec.preview_html = doc.inline_preview_html(width="100%", height="640px")

    @api.depends("registry_no", "full_name", "primary_site", "primary_site_label",
                 "morphology", "morphology_label", "date_of_diagnosis",
                 "age_at_diagnosis", "sex", "district", "summary_stage",
                 "vitality_status", "qc_score", "qc_status", "extraction_confidence")
    def _compute_summary_html(self):
        """ملخص مختصر يُطبع/يُنسخ — نفس مضمون ملخص الأداة المستقلة."""
        for rec in self:
            rows = [
                (_("رقم السجل"), rec.registry_no or "—"),
                (_("الاسم"), rec.full_name or rec._build_full_name() or "—"),
                (_("الرقم الوطني"), rec.national_id or "—"),
                (_("الجنس / العمر عند التشخيص"), "%s / %s" % (
                    dictionary.option_label("sex", rec.sex) or "—",
                    _("%s سنة") % rec.age_at_diagnosis if rec.age_at_diagnosis else "—")),
                (_("البلدية"), dictionary.option_label("district", rec.district) or "—"),
                (_("تاريخ التشخيص"), str(rec.date_of_diagnosis or "—")),
                (_("الموقع الأولي"), "%s — %s" % (
                    rec.primary_site or "?", rec.primary_site_label or
                    reference.site_label(rec.primary_site or "", "ar") or "—")),
                (_("الفحص النسيجي"), "%s — %s" % (
                    rec.morphology or "?", rec.morphology_label or
                    reference.morphology_label(rec.morphology or "", "ar") or "—")),
                (_("المرحلة الموجزة"), dictionary.option_label(
                    "summary_stage", rec.summary_stage) or "—"),
                (_("TNM سريري / مرضي"), "%s%s%s / %s%s%s" % (
                    rec.ct or "?", rec.cn or "?", rec.cm or "?",
                    rec.pt or "?", rec.pn or "?", rec.pm or "?")),
                (_("العلاج"), "، ".join(filter(None, [
                    _("جراحة") if rec.surgery_performed else "",
                    _("كيماوي") if rec.chemotherapy_given else "",
                    _("إشعاعي") if rec.radiotherapy_given else "",
                    _("هرموني") if rec.hormonal_given else "",
                    _("مناعي") if rec.immunotherapy_given else "",
                ])) or _("لم يُسجَّل")),
                (_("الحالة الحيوية"), dictionary.option_label(
                    "vitality_status", rec.vitality_status) or "—"),
                (_("الجودة"), "%s/100 — %s" % (
                    rec.qc_score or 0,
                    dictionary.option_label("qc_status", rec.qc_status or "not_run"))),
                (_("ثقة الاستخراج"), "%.1f%%" % (rec.extraction_confidence or 0)),
            ]
            body = "".join(
                '<tr><td style="padding:4px 10px 4px 0;color:#5b6b7f;white-space:nowrap;'
                'font-size:12px">%s</td>'
                '<td style="padding:4px 0;font-weight:600;font-size:13px">%s</td></tr>'
                % (label, value) for label, value in rows)
            rec.summary_html = (
                '<div style="direction:rtl;text-align:right;background:#fff;'
                'border:1px solid #e3e8ef;border-radius:8px;padding:10px 12px">'
                '<table style="width:100%%;border-collapse:collapse">%s</table></div>' % body)

    @api.depends("first_document_id", "first_document_id.extracted_text")
    def _compute_extracted_text_preview(self):
        for rec in self:
            doc = rec.first_document_id
            text = (doc.extracted_text or "").strip() if doc else ""
            if not text:
                rec.extracted_text_preview = _empty_panel(_(
                    "لا يوجد نص مستخرج لهذا المستند.\n"
                    "شغّل «التلخيص والاستخراج الذكي» أو استخدم «لصق النص يدوياً»."))
                continue
            snippet = text[:8000]
            hits = ""
            if doc.extraction_json:
                try:
                    import json
                    data = json.loads(doc.extraction_json)
                    hits = data.get("hits") or {}
                except (ValueError, TypeError):
                    hits = {}
            marks = []
            for name, hit in list(hits.items())[:120]:
                ev = ""
                if isinstance(hit, dict):
                    ev = hit.get("evidence") or ""
                else:
                    ev = getattr(hit, "evidence", "")
                if ev and len(ev) > 2 and ev in snippet:
                    marks.append(ev)
            body = _esc(snippet)
            for ev in sorted(set(marks), key=len, reverse=True)[:60]:
                body = body.replace(_esc(ev),
                                    "<mark style='background:#fff3bf;padding:0 2px'>"
                                    "%s</mark>" % _esc(ev), 1)
            rec.extracted_text_preview = (
                '<div style="direction:rtl;text-align:right">'
                '<div style="font-size:11.5px;color:#7b8798;padding-bottom:4px">'
                '%s %s</div>'
                '<pre style="white-space:pre-wrap;font-family:Consolas,monospace;'
                'font-size:12px;line-height:1.75;background:#fbfcfe;border:1px solid #e3e8ef;'
                'border-radius:8px;padding:10px;max-height:460px;overflow:auto;margin:0">%s'
                '</pre></div>' % (
                    _("أول 8000 حرف من النص المستخرج —"),
                    "" if len(text) <= 8000 else _("(من %s حرفاً)") % len(text), body))

    # ------------------------------------------------------------------ مساعدات
    def _build_full_name(self):
        self.ensure_one()
        return " ".join(filter(None, [self.first_name, self.father_name,
                                     self.grandfather_name, self.family_name])).strip()

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if "reporting_facility" not in res or not res.get("reporting_facility"):
            res["reporting_facility"] = (self.env.company.name or "").strip()
        if "notification_date" not in res:
            res["notification_date"] = fields.Date.context_today(self)
        if "vitality_status" not in res:
            res["vitality_status"] = "alive"
        if "data_entry_status" not in res:
            res["data_entry_status"] = "draft"
        if "qc_status" not in res:
            res["qc_status"] = "not_run"
        if "birth_date_known" not in res:
            res["birth_date_known"] = True
        return res

    # ------------------------------------------------------------------ الإجراءات
    def action_storage_location(self):
        """زر «مكان الملف المخزن» — يفتح صفحة الأرشيف (DMS + المسار على القرص)."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": "/cancer_registry/storage/%d" % self.id,
            "target": "new",
        }

    def action_open_archive_window(self):
        """بديل: قائمة مرفقات هذه الحالة داخل أودو."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("مرفقات %s") % self.registry_no,
            "res_model": "cancer.registry.document",
            "view_mode": "tree,form",
            "domain": [("case_id", "=", self.id)],
            "context": {"default_case_id": self.id},
            "target": "current",
        }

    def build_export_records(self):
        """يبني قائمة السجلات بصيغة نواة التصدير انطلاقاً من سجلات أودو."""
        records = []
        for rec in self:
            row = rec._as_record_dict()
            row["document_ids"] = ", ".join(rec.document_ids.mapped("name"))
            records.append(row)
        if not records:
            raise UserError(_("لا توجد سجلات لتصديرها."))
        return records

    def action_export_excel(self):
        """زر «حفظ كـ / تصدير» — Excel مطابق لقالب السجل الوطني (6 أوراق)."""
        import datetime
        import tempfile
        records = self.build_export_records()
        meta = {
            "facility": self.env.company.name,
            "author": self.env.user.name,
            "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "scope": _("السجلات المحددة (%s)") % len(records) if len(self) > 1
                     else _("سجل واحد"),
        }
        fd, tmp = tempfile.mkstemp(suffix=".xlsx", prefix="cancer_registry_")
        os.close(fd)
        try:
            path = excel_export.export_records(records, tmp, meta=meta)
        except Exception as exc:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise UserError(_("تعذّر إنشاء ملف Excel: %s") % exc)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        fname = _("cancer_registry_%s_%s.xlsx") % (
            self[:1].registry_no.replace("/", "-") if len(self) == 1 else "batch", stamp)
        with open(path, "rb") as fh:
            payload = base64.b64encode(fh.read())
        try:
            os.unlink(path)
        except OSError:
            pass
        att = self.env["ir.attachment"].create({
            "name": fname,
            "type": "binary",
            "datas": payload,
            "res_model": self._name,
            "res_id": self.id if len(self) == 1 else False,
            "mimetype": "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet",
            "public": False,
        })
        for rec in self:
            rec.message_post(
                body=_("تم إنشاء ملف التصدير: %s") % att.name,
                attachment_ids=[att.id])
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%d?download=true" % att.id,
            "target": "self",
        }

    def action_print_summary(self):
        """ملخص PDF/طباعة — يفتح صفحة الملخص القابلة للطباعة."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": "/cancer_registry/summary/%d" % self.id,
            "target": "new",
        }

    def action_open_treatments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("سطور العلاج — %s") % self.registry_no,
            "res_model": "cancer.registry.treatment",
            "view_mode": "tree,form",
            "domain": [("case_id", "=", self.id)],
            "context": {"default_case_id": self.id},
            "target": "new",
        }

    def action_lookup_icdo3(self):
        """يفتح جدول ICD-O-3 مفلتراً على رموز هذه الحالة."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("مرجع ICD-O-3"),
            "res_model": "cancer.registry.icdo3.topography",
            "view_mode": "tree,form",
            "domain": [("code", "like", (self.primary_site or "")[:3])],
            "target": "new",
        }


# ═══════════════════════════════════════════════════════════════════════════
#  المستند — المعاينة جنباً إلى جنب
# ═══════════════════════════════════════════════════════════════════════════
class CancerRegistryDocumentExt(models.Model):
    _inherit = "cancer.registry.document"

    preview_html = fields.Html(
        string="المعاينة", compute="_compute_preview_html",
        sanitize=False, readonly=True)
    text_preview_html = fields.Html(
        string="النص المستخرج", compute="_compute_preview_html",
        sanitize=False, readonly=True)
    download_url = fields.Char(string="رابط التنزيل", compute="_compute_preview_html")
    extracted_fields_count = fields.Integer(
        string="عدد الحقول المستخرجة", compute="_compute_extracted_summary")
    extracted_fields_summary = fields.Text(
        string="ملخص الحقول المستخرجة", compute="_compute_extracted_summary")

    @api.depends("extraction_json")
    def _compute_extracted_summary(self):
        import json as _json
        for rec in self:
            count, lines = 0, []
            if rec.extraction_json:
                try:
                    data = _json.loads(rec.extraction_json)
                except (ValueError, TypeError):
                    data = {}
                record = data.get("record") or data.get("values") or {}
                for key, value in record.items():
                    if key.startswith("_") or value in (None, "", []):
                        continue
                    fld = dictionary.FIELDS.get(key)
                    if not fld:
                        continue
                    count += 1
                    shown = value
                    if fld["type"] == "selection":
                        shown = dictionary.option_label(key, value) or value
                    elif fld["type"] == "boolean":
                        shown = _("نعم") if value else _("لا")
                    lines.append("%s: %s" % (fld["label_ar"], shown))
            rec.extracted_fields_count = count
            rec.extracted_fields_summary = "\n".join(lines[:120]) or ""

    def action_open_download(self):
        """يفتح المستند في تبويب جديد للتنزيل/الطباعة."""
        self.ensure_one()
        if not self.file_content:
            raise UserError(_("لا يوجد ملف ثنائي مرفق بهذا المستند."))
        return {
            "type": "ir.actions.act_url",
            "url": "/cancer_registry/doc/%d/content?download=true" % self.id,
            "target": "new",
        }

    def inline_preview_html(self, width="100%", height="620px"):
        """HTML للعرض داخل لوحة المعاينة: PDF/صورة في iframe + النص المستخرج."""
        self.ensure_one()
        if not self.file_content:
            return _empty_panel(_("لا يوجد ملف ثنائي — يوجد نص مستخرج فقط."))
        suffix = os.path.splitext(self.name or "")[1].lower()
        url = "/cancer_registry/doc/%d/content" % self.id
        is_image = suffix in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
        if is_image:
            body = ('<img src="%s" style="max-width:100%%;border:1px solid #e3e8ef;'
                    'border-radius:6px;background:#fff" alt="%s"/>' % (url, self.name))
        else:
            body = ('<iframe src="%s" style="width:%s;height:%s;border:1px solid #e3e8ef;'
                    'border-radius:6px;background:#fff" '
                    'title="%s"></iframe>' % (url, width, height, self.name))
        meta = (
            '<div style="direction:rtl;text-align:right;padding:6px 2px;font-size:12px;'
            'color:#5b6b7f">'
            '<b>%s</b> &nbsp;•&nbsp; %s &nbsp;•&nbsp; %s &nbsp;•&nbsp; '
            'المحرك: <code>%s</code> &nbsp;•&nbsp; الثقة: <b>%s%%</b>'
            '<br/><span style="color:#8a97a8;word-break:break-all">%s</span>'
            '</div>' % (
                self.name or "—",
                _("%s بايت") % f"{self.file_size:,}" if self.file_size else "—",
                _("%s صفحة") % self.pages_count if self.pages_count else "—",
                self.ocr_engine or _("لم يُقرأ بعد"),
                "%.1f" % (self.ocr_confidence or 0),
                self.storage_path or _("غير مؤرشف على القرص")))
        return ('<div style="direction:rtl">%s%s</div>' % (meta, body))

    @api.depends("file_content", "name", "extracted_text", "ocr_engine",
                 "ocr_confidence", "storage_path")
    def _compute_preview_html(self):
        for rec in self:
            rec.preview_html = rec.inline_preview_html(height="560px")
            rec.download_url = "/cancer_registry/doc/%d/content?download=true" % rec.id
            text = (rec.extracted_text or "").strip()
            if not text:
                rec.text_preview_html = _empty_panel(_(
                    "لم يُستخرج نص بعد.\nشغّل «التلخيص والاستخراج الذكي» من نموذج الحالة."))
            else:
                snippet = text[:6000]
                rec.text_preview_html = (
                    '<div style="direction:rtl;text-align:right">'
                    '<div style="font-size:12px;color:#5b6b7f;padding-bottom:4px">'
                    '%s %s</div>'
                    '<pre style="direction:rtl;text-align:right;white-space:pre-wrap;'
                    'font-family:monospace;font-size:12px;line-height:1.7;background:#fbfcfe;'
                    'border:1px solid #e3e8ef;border-radius:6px;padding:10px;max-height:520px;'
                    'overflow:auto;margin:0">%s</pre></div>' % (
                        _("أول 6000 حرف من النص المستخرج —"),
                        "" if len(text) <= 6000 else _("(من %s حرفاً)") % len(text),
                        _esc(snippet)))


# ═══════════════════════════════════════════════════════════════════════════
#  مشاكل الجودة — تلوين
# ═══════════════════════════════════════════════════════════════════════════
class CancerRegistryQcIssueExt(models.Model):
    _inherit = "cancer.registry.qc.issue"

    severity_color = fields.Integer(compute="_compute_severity_color")
    # مخزَّنة حتى يمكن التجميع/البحث بها في القوائم والتقارير
    rule_name = fields.Char(string="اسم القاعدة", compute="_compute_severity_color",
                            store=True, index=True)
    rule_family = fields.Char(string="عائلة القاعدة", compute="_compute_severity_color",
                              store=True, index=True)

    @api.depends("severity", "code")
    def _compute_severity_color(self):
        families = {"A": _("الاكتمال"), "B": _("الصيغة والمعايير"),
                    "C": _("المنطق والتسلسل"), "D": _("التكرار"),
                    "E": _("المستندات"), "F": _("الأسماء والبيانات الشخصية")}
        for rec in self:
            rec.severity_color = {"error": 1, "warning": 3, "info": 5}.get(rec.severity, 5)
            cat = quality_cat(rec.code)
            rec.rule_name = cat[1] if cat else ""
            rec.rule_family = families.get((rec.code or "?")[1:2], _("أخرى"))


def quality_cat(code):
    from . import cr_bridge
    return cr_bridge.quality.RULE_CATALOGUE.get(code or "")


def _esc(value):
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _empty_panel(message):
    return (
        '<div style="direction:rtl;text-align:right;background:#fbfcfe;'
        'border:1px dashed #c8d2e0;border-radius:8px;padding:26px 18px;'
        'color:#7b8798;font-size:13px;white-space:pre-line">%s</div>'
        % _esc(message))

# -*- coding: utf-8 -*-
"""
معالج «حفظ كـ / تصدير»
========================
يُنتج ملف Excel مطابقاً لقالب السجل الوطني — نفس الملف الذي تنتجه الأداة
المستقلة، بنفس ترتيب الأعمدة، ونفس الأوراق الست:

    1. السجل                 — صف لكل حالة، 80 عموداً بترتيب القاموس
    2. العلاج                — سطر لكل دورة علاج مرتبطة بحالة
    3. جودة البيانات         — كل مشكلة مع رمز القاعدة والإصلاح المقترح
    4. ملخص الفحص            — إحصاءات التغطية والتوزيعات
    5. قاموس الحقول          — تعريف الحقل ونوعه وإلزاميته وقائمته ومرجعه
    6. مرجع ICD-O-3          — جداول المواقع والفحص النسيجي والمرحلة
"""

import base64
import os
import tempfile
from datetime import datetime

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..models import cr_bridge
dictionary = cr_bridge.dictionary
excel_export = cr_bridge.excel_export
quality = cr_bridge.quality

SCOPES = [
    ("all", "كل السجلات"),
    ("validated", "المعتمدة فقط"),
    ("draft", "غير المكتملة / المسودة"),
    ("selection", "المحددة في القائمة الحالية"),
    ("period", "حسب فترة تاريخ التشخيص"),
    ("year", "حسب سنة التشخيص"),
    ("district", "حسب البلدية"),
    ("needs_fix", "التي بها أخطاء جودة (لم تُعتمد)"),
    ("recent", "المُدخلة خلال آخر 30 يوماً"),
]


class CancerRegistryExportWizard(models.TransientModel):
    _name = "cancer.registry.export.wizard"
    _description = "تصدير سجل السرطان إلى Excel / الأرشيف الوطني"

    scope = fields.Selection(SCOPES, string="نطاق التصدير", default="all",
                             required=True)
    date_from = fields.Date(string="من تاريخ التشخيص")
    date_to = fields.Date(string="إلى تاريخ التشخيص")
    diagnosis_year = fields.Integer(
        string="سنة التشخيص", default=lambda self: fields.Date.context_today(self).year)
    district = fields.Selection(selection="_sel_district", string="البلدية")
    qc_min = fields.Integer(
        string="أدنى درجة جودة", default=0,
        help="0 = بلا حد. مثلاً 80 يعني تصدير السجلات التي اجتازت الفحص بـ80 أو أكثر.")
    only_validated = fields.Boolean(string="المعتمدة فقط", default=False)

    include_qc = fields.Boolean(string="ورقة «جودة البيانات»", default=True)
    include_dictionary = fields.Boolean(string="ورقة «قاموس الحقول»", default=True)
    include_refdata = fields.Boolean(string="ورقة «مرجع ICD-O-3»", default=True)

    facility = fields.Char(
        string="الجهة المصدِّرة",
        default=lambda self: self.env.company.name or
        _("مكتب سجل السرطان — المعهد القومي للأورام، صبراتة"))
    author = fields.Char(string="أعدّه", default=lambda self: self.env.user.name)
    period_label = fields.Char(string="وصف الفترة (يظهر في الترويسة)")

    records_count = fields.Integer(string="عدد السجلات", compute="_compute_count")
    preview_html = fields.Html(string="معاينة", compute="_compute_count",
                               sanitize=False, readonly=True)
    attachment_id = fields.Many2one("ir.attachment", string="الملف المُنشأ",
                                    readonly=True)
    filename = fields.Char(string="اسم الملف", readonly=True)

    @api.model
    def _sel_district(self):
        return dictionary.option_pairs("district", self.env.lang or "ar_AR")

    @api.depends("scope", "date_from", "date_to", "diagnosis_year", "district",
                 "qc_min", "only_validated")
    def _compute_count(self):
        for wiz in self:
            domain = wiz._domain()
            Case = wiz.env["cancer.registry.case"]
            records = Case.search(domain)
            wiz.records_count = len(records)
            wiz.preview_html = wiz._render_preview(records)

    def _domain(self):
        scope = self.scope or "all"
        domain = []
        active_ids = self.env.context.get("active_ids") or []
        active_model = self.env.context.get("active_model")

        if scope == "selection" and active_ids and \
                active_model == "cancer.registry.case":
            domain.append(("id", "in", active_ids))
        elif scope == "validated":
            domain.append(("data_entry_status", "=", "validated"))
        elif scope == "draft":
            domain.append(("data_entry_status", "in", ("new", "extracted", "review")))
        elif scope == "needs_fix":
            domain.append(("qc_status", "=", "error"))
        elif scope == "period":
            if self.date_from:
                domain.append(("date_of_diagnosis", ">=", self.date_from))
            if self.date_to:
                domain.append(("date_of_diagnosis", "<=", self.date_to))
        elif scope == "year":
            if self.diagnosis_year:
                domain.append(("diagnosis_year", "=", self.diagnosis_year))
        elif scope == "district":
            if self.district:
                domain.append(("district", "=", self.district))
        elif scope == "recent":
            from datetime import timedelta
            since = fields.Date.context_today(self) - timedelta(days=30)
            domain.append(("create_date", ">=", since))

        if self.only_validated:
            domain.append(("data_entry_status", "=", "validated"))
        if self.qc_min and self.qc_min > 0:
            domain.append(("qc_score", ">=", self.qc_min))
        return domain

    def _render_preview(self, records):
        scope_label = dict(self._fields["scope"].selection(self)).get(self.scope, "")
        by_status = {}
        by_year = {}
        for rec in records:
            by_status[rec.qc_status or "not_run"] = by_status.get(
                rec.qc_status or "not_run", 0) + 1
            by_year[rec.diagnosis_year or 0] = by_year.get(rec.diagnosis_year or 0, 0) + 1
        avg = (sum(records.mapped("qc_score")) / len(records)) if records else 0

        def chips(mapping, color="#eaf1f9", fg="#123a63"):
            if not mapping:
                return "<span class='muted'>—</span>"
            return " ".join(
                "<span class='pill' style='background:%s;color:%s'>%s: <b>%s</b></span>"
                % (color, fg, _esc(dictionary.option_label("qc_status", k) or k), v)
                for k, v in sorted(mapping.items(), key=lambda kv: -kv[1]))

        rows = "".join(
            "<tr><td><code>%s</code></td><td>%s</td><td>%s</td><td>%s</td>"
            "<td style='text-align:left'><b>%s</b>/100</td></tr>" % (
                _esc(r.registry_no), _esc(r.full_name or r._build_full_name()),
                _esc(r.primary_site_label or r.primary_site or "—"),
                _esc(str(r.date_of_diagnosis or "—")), r.qc_score or 0)
            for r in records[:25])

        return (_STYLE +
                "<div class='card'><h2>ملخص التصدير</h2>"
                "<p>النطاق: <b>%s</b> &nbsp;•&nbsp; السجلات: <b>%s</b> "
                "&nbsp;•&nbsp; متوسط الجودة: <b>%.1f/100</b></p>"
                "<p>%s</p><p>%s</p></div>"
                "<div class='card'><h2>أول %s سجل في النطاق</h2>"
                "<table><thead><tr><th>الرقم</th><th>الاسم</th><th>الموقع</th>"
                "<th>التشخيص</th><th>الجودة</th></tr></thead><tbody>%s</tbody></table>"
                "%s</div></div>" % (
                    _esc(scope_label), len(records), avg,
                    chips(by_status),
                    "<span class='muted'>حسب سنة التشخيص: %s</span>" % ", ".join(
                        "%s (%s)" % (k, v) for k, v in sorted(by_year.items())
                        if k) or "—",
                    min(25, len(records)), rows,
                    "" if len(records) <= 25 else
                    "<p class='muted'>… و%s سجل آخر</p>" % (len(records) - 25)))

    # ------------------------------------------------------------------
    def action_export(self):
        self.ensure_one()
        Case = self.env["cancer.registry.case"]
        records = Case.search(self._domain())
        if not records:
            raise UserError(_("لا توجد سجلات مطابقة لهذا النطاق."))

        rows = []
        for rec in records:
            row = rec._as_record_dict()
            row["document_ids"] = ", ".join(rec.document_ids.mapped("name"))
            rows.append(row)

        period = (self.period_label or "").strip()
        if not period:
            if self.scope == "year":
                period = _("سنة التشخيص %s") % self.diagnosis_year
            elif self.scope == "period":
                period = "%s → %s" % (self.date_from or "…", self.date_to or "…")
            elif self.scope == "district":
                period = _("بلدية %s") % (
                    dictionary.option_label("district", self.district) or "—")
            else:
                period = dict(self._fields["scope"].selection(self)).get(self.scope, "")

        meta = {
            "facility": self.facility or self.env.company.name,
            "author": self.author or self.env.user.name,
            "period": period,
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "scope": period,
            "records": len(rows),
            "validated_only": bool(self.only_validated),
        }

        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in (period or ""))
        fname = "CancerRegistry_%s_%s.xlsx" % (safe[:40] or "export", stamp)

        fd, tmp = tempfile.mkstemp(suffix=".xlsx", prefix="cr_export_")
        os.close(fd)
        try:
            path = excel_export.export_records(
                rows, tmp, meta=meta,
                include_qc=self.include_qc,
                include_dictionary=self.include_dictionary,
                include_refdata=self.include_refdata)
            with open(path, "rb") as fh:
                payload = base64.b64encode(fh.read())
            size = os.path.getsize(path)
        except Exception as exc:
            raise UserError(_("تعذّر إنشاء ملف Excel: %s") % exc)
        finally:
            for p in {tmp, str(path)}:
                try:
                    if p and os.path.exists(p):
                        os.unlink(p)
                except OSError:
                    pass

        if self.attachment_id:
            self.attachment_id.unlink()
        att = self.env["ir.attachment"].create({
            "name": fname,
            "type": "binary",
            "datas": payload,
            "res_model": self._name,
            "res_id": self.id,
            "mimetype": "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet",
            "description": _("%s سجل — %s — %s") % (len(rows), period, meta["facility"]),
        })
        self.write({"attachment_id": att.id, "filename": fname})

        # تدقيق في السجلات المُصدَّرة
        for rec in records[:200]:
            rec.message_post(body=_("تم تصديره في %s (%s سجل)") % (fname, len(rows)))

        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%d?download=true" % att.id,
            "target": "self",
        }

    def action_download(self):
        self.ensure_one()
        if not self.attachment_id:
            raise UserError(_("أنشئ الملف أولاً بزر «تصدير»."))
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%d?download=true" % self.attachment_id.id,
            "target": "self",
        }

    def action_export_and_archive(self):
        """يصدر الملف ويحفظ نسخة في مجلد أرشيف التصديرات على القرص."""
        self.ensure_one()
        res = self.action_export()
        try:
            from ..models import cr_bridge
            out_dir = cr_bridge.storage.export_dir()
            target = out_dir / (self.filename or "export.xlsx")
            target.write_bytes(base64.b64decode(self.attachment_id.datas))
            cr_bridge.storage.audit(
                "export.excel.odoo",
                details={"path": str(target), "records": self.records_count,
                         "scope": self.scope, "user": self.env.user.login})
        except Exception:                                   # pragma: no cover
            pass
        return res


def _esc(value):
    return (str(value if value is not None else "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


_STYLE = """<style>
.cr-ex * { box-sizing: border-box }
.cr-ex { direction: rtl; text-align: right; font-size: 13px; color: #1c2b3a }
.cr-ex .card { background:#fff; border:1px solid #e2e8f0; border-radius:10px;
               padding:12px 14px; margin-bottom:12px }
.cr-ex .card h2 { font-size:14px; margin:0 0 8px; color:#123a63;
                  border-bottom:2px solid #eaf1f9; padding-bottom:6px }
.cr-ex table { width:100%; border-collapse:collapse }
.cr-ex th, .cr-ex td { padding:6px 8px; border-bottom:1px solid #eef2f7;
                       text-align:right; vertical-align:top }
.cr-ex th { background:#f7fafd; color:#4a5b70; font-weight:600; font-size:11.5px }
.cr-ex code { font-family:Consolas,"Courier New",monospace; direction:ltr;
              unicode-bidi:embed; background:#f4f7fb; padding:1px 6px; border-radius:4px }
.cr-ex .muted { color:#7b8798 }
.cr-ex .pill { display:inline-block; padding:2px 9px; border-radius:999px;
               font-size:11px; font-weight:600; margin-left:4px }
</style><div class="cr-ex">"""

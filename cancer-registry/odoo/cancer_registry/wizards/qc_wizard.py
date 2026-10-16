# -*- coding: utf-8 -*-
"""
معالج «فحص جودة البيانات»
===========================
يعرض نتيجة ~40 قاعدة جودة في نافذة واحدة قابلة للنقر:
كل مشكلة تعرض رمز القاعدة، الحقل، الوصف، الإصلاح المقترح، والمرجع المعياري.

العوائل:
  A — الاكتمال (الحقول الإلزامية والموصى بها)
  B — الصيغة والمعايير (الرقم الوطني، ICD-O-3، TNM، التواريخ)
  C — المنطق والتسلسل (الميلاد قبل التشخيص، الوفاة، توافق الجنس مع الموقع)
  D — التكرار (نفس الرقم الوطني + الموقع + التاريخ)
  E — المستندات (وجود مستند مصدر، جودة القراءة)
  F — الأسماء والبيانات الشخصية (تجزئة الاسم، طول غير منطقي)
"""

from odoo import api, fields, models, _

from ..models import cr_bridge
dictionary = cr_bridge.dictionary
quality = cr_bridge.quality
reference = cr_bridge.reference

SEV_STYLE = {
    "error": ("#b3261e", "#fdf5f4", "#f0c9c4", _("خطأ")),
    "warning": ("#8a5a09", "#fffaf0", "#f3e0bd", _("تحذير")),
    "info": ("#123a63", "#f4f8fd", "#d5e3f2", _("ملاحظة")),
}

STATUS_STYLE = {
    "pass": ("#1a7f4b", _("سليم")),
    "warning": ("#a86a12", _("به تحذيرات")),
    "error": ("#b3261e", _("به أخطاء")),
    "not_run": ("#7b8798", _("لم يُفحص")),
}

FAMILIES = {
    "A": _("الاكتمال"),
    "B": _("الصيغة والمعايير"),
    "C": _("المنطق والتسلسل الزمني"),
    "D": _("السجلات المكررة"),
    "E": _("المستندات والمصدر"),
    "F": _("الأسماء والبيانات الشخصية"),
}


class CancerRegistryQcWizard(models.TransientModel):
    _name = "cancer.registry.qc.wizard"
    _description = "نتيجة فحص جودة بيانات سجل السرطان"
    _order = "id desc"

    case_id = fields.Many2one("cancer.registry.case", string="السجل",
                              required=True, ondelete="cascade")
    registry_no = fields.Char(related="case_id.registry_no", string="رقم السجل")
    score = fields.Integer(string="الدرجة من 100", readonly=True)
    status = fields.Selection([
        ("not_run", "لم يُفحص"), ("pass", "سليم"),
        ("warning", "به تحذيرات"), ("error", "به أخطاء"),
    ], string="النتيجة", readonly=True)
    errors_count = fields.Integer(string="عدد الأخطاء", readonly=True)
    warnings_count = fields.Integer(string="عدد التحذيرات", readonly=True)
    report_text = fields.Text(string="التقرير النصي", readonly=True)
    report_html = fields.Html(string="التقرير", compute="_compute_report_html",
                              sanitize=False, readonly=True)
    issue_ids = fields.One2many("cancer.registry.qc.issue", "case_id",
                                string="المشاكل المسجّلة", readonly=True)
    coverage_note = fields.Char(string="ملاحظة التغطية", compute="_compute_report_html")

    @api.depends("case_id", "score", "status", "errors_count", "warnings_count",
                 "issue_ids", "issue_ids.resolved")
    def _compute_report_html(self):
        for wiz in self:
            wiz.report_html = wiz._render()
            dod = wiz.case_id.date_of_diagnosis
            if dod and dod.year < quality.REGISTRY_COVERAGE_FROM:
                wiz.coverage_note = _(
                    "سنة التشخيص %s أقدم من بداية التغطية الإلزامية للسجل (%s) — "
                    "قد يكون هذا تسجيل رجعي."
                ) % (dod.year, quality.REGISTRY_COVERAGE_FROM)
            else:
                wiz.coverage_note = False

    def _render(self):
        self.ensure_one()
        color, label = STATUS_STYLE.get(self.status or "not_run", ("#7b8798", "—"))
        issues = self.issue_ids.sorted(lambda i: (
            {"error": 0, "warning": 1, "info": 2}.get(i.severity, 9), i.code))

        # تجميع حسب العائلة
        grouped = {}
        for iss in issues:
            fam = (iss.code or "?")[1:2]
            grouped.setdefault(fam, []).append(iss)

        blocks = []
        for fam in sorted(grouped):
            rows = ""
            for iss in grouped[fam]:
                sev_color, bg, border, sev_label = SEV_STYLE.get(
                    iss.severity, SEV_STYLE["info"])
                cat = quality.RULE_CATALOGUE.get(iss.code or "")
                rule_name = cat[1] if len(cat) > 1 else ""
                rule_ref = cat[3] if len(cat) > 3 else ""
                rows += (
                    "<tr style='background:%s'>"
                    "<td style='white-space:nowrap'>"
                    "<code style='background:#fff;border:1px solid %s;border-radius:4px;"
                    "padding:1px 6px;color:%s'>%s</code>"
                    "<div class='muted' style='font-size:11px;margin-top:3px'>%s</div></td>"
                    "<td style='white-space:nowrap;color:%s;font-weight:600'>%s</td>"
                    "<td><b>%s</b><br/><span class='muted mono' style='font-size:11px'>"
                    "%s</span></td>"
                    "<td>%s</td>"
                    "<td style='font-size:12px;color:#41526a;background:#fff;"
                    "border-radius:6px'>%s</td>"
                    "<td class='muted' style='font-size:11px'>%s</td>"
                    "</tr>" % (
                        bg, border, sev_color, _esc(iss.code), _esc(rule_name),
                        sev_color, _esc(sev_label),
                        _esc(iss.field_label or dictionary.label(iss.field_name)),
                        _esc(iss.field_name or ""),
                        _esc(iss.message), _esc(iss.fix or ""), _esc(rule_ref)))
            blocks.append(
                "<div class='card'><h2>%s — %s</h2>"
                "<table><thead><tr><th>القاعدة</th><th>الخطورة</th><th>الحقل</th>"
                "<th>المشكلة</th><th>الإصلاح المقترح</th><th>المرجع</th></tr></thead>"
                "<tbody>%s</tbody></table></div>"
                % (_esc(FAMILIES.get(fam, _("أخرى"))), _esc(fam), rows))

        if not blocks:
            blocks.append(
                "<div class='card' style='border-color:#bfe3cd;background:#f4fbf7'>"
                "<h2 style='color:#1a7f4b;border-color:#d8ecdf'>لا توجد مشاكل ✓</h2>"
                "<p>اجتاز السجل كل قواعد الفحص (%s قاعدة).</p></div>"
                % len(quality.RULE_CATALOGUE))

        # ملخص الاكتمال: الحقول الإلزامية
        rec = self.case_id._as_record_dict() if self.case_id else {}
        missing_req = [dictionary.label(n) for n in dictionary.REQUIRED_FIELDS
                       if not rec.get(n)]
        req_block = ""
        if missing_req:
            req_block = (
                "<div class='card' style='border-color:#f0c9c4;background:#fdf5f4'>"
                "<h2 style='color:#b3261e;border-color:#f6dedb'>حقول إلزامية ناقصة (%s)</h2>"
                "<p>%s</p></div>" % (len(missing_req), _esc("، ".join(missing_req))))

        head = (
            "<div class='card' style='text-align:center'>"
            "<div style='font-size:44px;font-weight:800;color:%s;line-height:1'>%s"
            "<span style='font-size:18px;color:#7b8798'>/100</span></div>"
            "<div style='font-size:14px;font-weight:700;color:%s;margin-top:4px'>%s</div>"
            "<div class='muted' style='font-size:12.5px;margin-top:6px'>"
            "%s خطأ &nbsp;•&nbsp; %s تحذير &nbsp;•&nbsp; %s قاعدة مفحوصة</div>"
            "</div>"
            % (color, self.score or 0, color, _esc(label),
               self.errors_count or 0, self.warnings_count or 0,
               len(quality.RULE_CATALOGUE)))

        return _STYLE + head + req_block + "".join(blocks) + "</div>"

    # ------------------------------------------------------------------
    def action_rerun(self):
        self.ensure_one()
        report = self.case_id.run_quality_check()
        self.write({"score": report.get("score", 0), "status": report.get("status"),
                    "errors_count": report.get("errors", 0),
                    "warnings_count": report.get("warnings", 0),
                    "report_text": report.get("text", "")})
        return {
            "type": "ir.actions.act_window", "res_model": self._name,
            "res_id": self.id, "view_mode": "form", "target": "new",
            "context": self.env.context,
        }

    def action_mark_resolved(self):
        """يعالج تلقائياً كل ما يمكن معالجته (الحقول المشتقة) ثم يعيد الفحص."""
        self.ensure_one()
        self.case_id._recompute_derived()
        return self.action_rerun()

    def action_show_rules(self):
        """دليل قواعد الجودة كاملاً."""
        rows = ""
        # بنية القاعدة: (العائلة، الاسم، الخطورة، المرجع المعياري)
        for code, cat in sorted(quality.RULE_CATALOGUE.items()):
            family = cat[0] if cat else ""
            name = cat[1] if len(cat) > 1 else ""
            sev = cat[2] if len(cat) > 2 else ""
            ref = cat[3] if len(cat) > 3 else ""
            sev_color = SEV_STYLE.get(sev, SEV_STYLE["info"])[0]
            sev_label = SEV_STYLE.get(sev, SEV_STYLE["info"])[3]
            rows += ("<tr><td><code>%s</code></td>"
                     "<td style='color:%s;font-weight:600'>%s</td>"
                     "<td><b>%s</b></td><td class='muted'>%s</td>"
                     "<td class='muted' style='font-size:11.5px'>%s</td></tr>"
                     % (_esc(code), sev_color, _esc(sev_label),
                        _esc(name), _esc(family), _esc(ref)))
        body = (_STYLE + "<div class='card'><h2>دليل قواعد فحص الجودة (%s قاعدة)</h2>"
                "<table><thead><tr><th>الرمز</th><th>الخطورة</th><th>القاعدة</th>"
                "<th>العائلة</th><th>المرجع المعياري</th></tr></thead>"
                "<tbody>%s</tbody></table>"
                "</div></div>" % (len(quality.RULE_CATALOGUE), rows))
        self.ensure_one()
        self.write({"report_text": body})
        return {
            "type": "ir.actions.act_window",
            "name": _("دليل قواعد الجودة"),
            "res_model": "cancer.registry.qc.rules.wizard",
            "view_mode": "form",
            "res_id": self.env["cancer.registry.qc.rules.wizard"].create(
                {"body_html": body}).id,
            "target": "new",
        }


class CancerRegistryQcRulesWizard(models.TransientModel):
    _name = "cancer.registry.qc.rules.wizard"
    _description = "دليل قواعد الجودة"

    body_html = fields.Html(string="القواعد", sanitize=False, readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        # عند الفتح مباشرة من القائمة (بلا حالة مرتبطة) ابنِ الدليل كاملاً
        if "body_html" in fields_list and not res.get("body_html"):
            res["body_html"] = self._build_catalogue()
        return res

    @api.model
    def _build_catalogue(self):
        rows = ""
        for code, cat in sorted(quality.RULE_CATALOGUE.items()):
            family = cat[0] if cat else ""
            name = cat[1] if len(cat) > 1 else ""
            sev = cat[2] if len(cat) > 2 else ""
            ref = cat[3] if len(cat) > 3 else ""
            sev_color, _bg, _bd, sev_label = SEV_STYLE.get(sev, SEV_STYLE["info"])
            rows += ("<tr><td><code>%s</code></td>"
                     "<td style='color:%s;font-weight:600'>%s</td>"
                     "<td><b>%s</b></td><td class='muted'>%s</td>"
                     "<td class='muted' style='font-size:11.5px'>%s</td></tr>"
                     % (_esc(code), sev_color, _esc(sev_label), _esc(name),
                        _esc(family), _esc(ref)))
        by_sev = {}
        for cat in quality.RULE_CATALOGUE.values():
            sev = cat[2] if len(cat) > 2 else "?"
            by_sev[sev] = by_sev.get(sev, 0) + 1
        chips = " ".join(
            "<span class='pill' style='background:%s;color:#fff'>%s: <b>%s</b></span>"
            % (SEV_STYLE.get(sev, SEV_STYLE["info"])[0],
               SEV_STYLE.get(sev, SEV_STYLE["info"])[3], n)
            for sev, n in sorted(by_sev.items()))
        return (_STYLE +
                "<div class='card'><h2>دليل قواعد فحص الجودة</h2>"
                "<p>عدد القواعد: <b>%s</b> &nbsp; %s</p>"
                "<p class='muted'>رمز القاعدة: <code>Q-&lt;العائلة&gt;&lt;الرقم&gt;</code> — "
                "A الاكتمال، B الصيغة والمعايير، C المنطق والتسلسل الزمني، "
                "D السجلات المكررة، E المستندات والمصدر، F الأسماء والبيانات الشخصية.</p>"
                "</div>"
                "<div class='card'><table><thead><tr><th>الرمز</th><th>الخطورة</th>"
                "<th>القاعدة</th><th>العائلة</th><th>المرجع المعياري</th></tr></thead>"
                "<tbody>%s</tbody></table></div></div>"
                % (len(quality.RULE_CATALOGUE), chips, rows))


def _esc(value):
    return (str(value if value is not None else "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


_STYLE = """<style>
.cr-qc * { box-sizing: border-box }
.cr-qc { direction: rtl; text-align: right; font-size: 13px; color: #1c2b3a }
.cr-qc .card { background:#fff; border:1px solid #e2e8f0; border-radius:10px;
               padding:12px 14px; margin-bottom:12px }
.cr-qc .card h2 { font-size:14px; margin:0 0 8px; color:#123a63;
                  border-bottom:2px solid #eaf1f9; padding-bottom:6px }
.cr-qc table { width:100%; border-collapse:collapse }
.cr-qc th, .cr-qc td { padding:7px 8px; border-bottom:1px solid #eef2f7;
                       text-align:right; vertical-align:top }
.cr-qc th { background:#f7fafd; color:#4a5b70; font-weight:600; font-size:11.5px }
.cr-qc code, .cr-qc .mono { font-family:Consolas,"Courier New",monospace;
                            direction:ltr; unicode-bidi:embed; font-size:12px }
.cr-qc .muted { color:#7b8798 }
</style><div class="cr-qc">"""

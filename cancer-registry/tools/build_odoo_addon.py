#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
مولّد وحدة أودو من قاموس الحقول
================================
يضمن أن وحدة أودو والأداة المستقلة تستخدمان **نفس** القاموس حرفياً:

    python3 tools/build_odoo_addon.py

يقوم بـ:
  1) نسخ crcore/ داخل الوحدة (لتصبح مستقلة وقابلة للتوزيع كملف مضغوط)
  2) توليد models/cancer_registry_case.py من القاموس
  3) توليد data/icdo3_topography_data.xml و icdo3_morphology_data.xml
  4) توليد security/ir.model.access.csv

لا تشغّله إلا إذا غيّرت القاموس؛ الملفات المولَّدة موجودة في المستودع وجاهزة.
"""

from __future__ import annotations

import csv
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ADDON = ROOT / "odoo" / "cancer_registry"
CORE = ROOT / "crcore"

from crcore import dictionary as dic                     # noqa: E402
from crcore import reference as ref                      # noqa: E402

HEADER = '''# -*- coding: utf-8 -*-
# =============================================================================
#  هذا الملف مُولَّد آلياً من crcore/dictionary.py
#  للتجديد:   python3 tools/build_odoo_addon.py
#  لا تعدّل الحقول هنا يدوياً — عدّل القاموس ثم أعد التوليد، فتتطابق
#  وحدة أودو مع الأداة المستقلة ومع ملف Excel المُصدَّر.
# =============================================================================
'''

# حقول تُكتب يدوياً في القالب لأنها تحتاج تعريفاً خاصاً (index / default / related)
EXPLICIT_FIELDS = {"registry_no", "name", "created_on", "written_on"}

# الحقول التي تُتتبّع تغييراتها في سجل المحادثات (chatter)
TRACKED_SELECTIONS = {"sex", "vitality_status", "data_entry_status", "qc_status",
                      "summary_stage", "district", "basis_of_diagnosis"}

TYPE_MAP = {
    "char": "fields.Char",
    "text": "fields.Text",
    "date": "fields.Date",
    "datetime": "fields.Datetime",
    "integer": "fields.Integer",
    "float": "fields.Float",
    "boolean": "fields.Boolean",
    "binary": "fields.Binary",
}


def field_line(name: str, f: dict) -> str:
    t = f["type"]
    label = f["label_ar"].replace('"', "'")
    args = [f'string="{label}"']

    if t == "selection":
        args.insert(0, f'selection="_sel_{name}"')
        if f["required"]:
            args.append("required=True")
        if name in TRACKED_SELECTIONS:
            args.append("tracking=True")
        return f"    {name} = fields.Selection({', '.join(args)})\n"

    if t == "one2many":
        return (f'    {name} = fields.One2many("cancer.registry.document", "case_id", '
                f'string="{label}")\n')

    ctor = TYPE_MAP.get(t, "fields.Char")
    if t == "char":
        args.append(f"size={f['max_len']}")
    if t == "text":
        args.append("translate=False")
    if t == "float":
        args.append("digits=(5, 2)")
    if f["required"] and t in ("char", "text", "date"):
        args.append("required=True")
    if t in ("datetime",):
        args.append("readonly=True")

    # help واحد فقط (أودو لا يقبل وسيطاً مكرراً) — ندمج الشرح مع الصيغة
    help_parts = []
    if f.get("help_ar"):
        help_parts.append(f["help_ar"].replace('"', "'")[:150])
    if t == "char" and f.get("pattern"):
        help_parts.append(f"الصيغة المقبولة: {f['pattern']}")
    if f.get("ref"):
        help_parts.append(f"المرجع: {f['ref']}")
    if help_parts:
        merged = " — ".join(help_parts)
        args.append(f'help=r"{merged}"')
    return f"    {name} = {ctor}({', '.join(args)})\n"


def build_model() -> str:
    out = [HEADER]
    out.append("""from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

from . import cr_bridge
dictionary = cr_bridge.dictionary
reference = cr_bridge.reference
extractor = cr_bridge.extractor
quality = cr_bridge.quality
storage = cr_bridge.storage
pipeline = cr_bridge.pipeline


class CancerRegistryCase(models.Model):
    _name = "cancer.registry.case"
    _description = "حالة سجل السرطان"
    _order = "date_of_diagnosis desc, id desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_names_search = ["registry_no", "full_name", "national_id", "medical_file_no"]

    # --------------------------------------------------------------- المعرّف
    name = fields.Char(related="registry_no", store=True, string="المرجع")

    # ------------------------------------------------- الحقول من القاموس
""")
    for group, names in dic.GROUPS.items():
        out.append(f"    # ═══ {group} ═══\n")
        for n in names:
            if n in EXPLICIT_FIELDS:
                continue   # تُعرَّف صراحةً في قسم «حقول إضافية خاصة بأودو»
            out.append(field_line(n, dic.FIELDS[n]))
        out.append("\n")

    out.append('''    # ------------------------------------------------- حقول إضافية خاصة بأودو
    registry_no = fields.Char(
        string="رقم السجل في المكتب", required=True, copy=False, readonly=True,
        index=True, default=lambda self: _("New"), tracking=True)

    # طوابع زمنية مطابقة للأداة المستقلة — مرتبطة بحقول أودو الأصلية
    created_on = fields.Datetime(
        string="تاريخ الإنشاء", related="create_date", store=True, readonly=True)
    written_on = fields.Datetime(
        string="آخر تعديل", related="write_date", store=True, readonly=True)
    treatment_ids = fields.One2many(
        "cancer.registry.treatment", "case_id", string="سطور العلاج")
    qc_issue_ids = fields.One2many(
        "cancer.registry.qc.issue", "case_id", string="مشاكل الجودة")
    active = fields.Boolean(string="نشط", default=True)
    company_id = fields.Many2one("res.company", string="الجهة",
                                 default=lambda self: self.env.company)

    # ------------------------------------------------- حسابات
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("registry_no", _("New")) == _("New"):
                vals["registry_no"] = self.env["ir.sequence"].next_by_code(
                    "cancer.registry.case") or _("New")
        return super().create(vals_list)

    # ------------------------------------------------- قوائم الاختيار
    #   كلها تُقرأ من القاموس مباشرة — لا تكرار للتعريفات
''')
    for name, f in dic.FIELDS.items():
        if f["type"] == "selection" and f["options"]:
            out.append(f'''    @api.model
    def _sel_{name}(self):
        return dictionary.option_pairs("{name}", self.env.lang or "ar_AR")

''')

    out.append('''    # ------------------------------------------------- الأزرار والإجراءات
    def action_upload_document(self):
        """زر «رفع الملفات» — يفتح مدير المرفقات على مجلد الأرشيف."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("رفع مستند ممسوح ضوئياً"),
            "res_model": "cancer.registry.document",
            "view_mode": "form",
            "target": "new",
            "context": {"default_case_id": self.id},
        }

    def action_auto_extract(self):
        """زر «التلخيص والاستخراج الذكي» — OCR + استخراج + تفريغ في الحقول."""
        self.ensure_one()
        docs = self.document_ids.filtered(lambda d: d.extracted_text or d.file_content)
        if not docs:
            raise UserError(_(
                "لا يوجد مستند مرفق بهذه الحالة.\\n"
                "ارفع التقرير الممسوح ضوئياً أولاً بزر «رفع الملفات»."))
        record, warnings = {}, []
        for doc in docs:
            res = doc.run_extraction()
            for k, v in (res.get("record") or {}).items():
                if k not in record and v not in (None, "", []):
                    record[k] = v
            warnings += res.get("warnings") or []
            self.extraction_method = res.get("engine", "")
            self.extraction_confidence = res.get("confidence", 0.0)
        filled = self._apply_extracted(record)
        if not filled:
            raise UserError(_("لم يُستخرج أي حقل جديد. راجع جودة المسح أو استخدم «لصق النص يدوياً»."))
        filled["data_entry_status"] = "extracted"
        self.write(filled)
        self._recompute_derived()
        msg = _("تم استخراج %s حقل من %s مستند (ثقة %s%%).") % (
            len(filled), len(docs), self.extraction_confidence)
        if warnings:
            msg += "\\n" + "\\n".join("• " + w for w in warnings[:6])
        self.message_post(body=msg, subtype_xmlid="mail.mt_note")
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"title": _("الاستخراج الذكي"), "message": msg[:220],
                           "type": "success", "sticky": False}}

    def action_extract_from_text(self):
        """معالج لصق النص يدوياً (عند تعذّر OCR)."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("استخراج من نص ملصوق"),
            "res_model": "cancer.registry.extract.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_case_id": self.id},
        }

    def action_data_quality_check(self):
        """زر «جودة البيانات» — يفحص الاكتمال والصيغة والمنطق والمعايير."""
        self.ensure_one()
        report = self.run_quality_check()
        return {
            "type": "ir.actions.act_window",
            "name": _("نتيجة فحص الجودة — %s/100") % report.get("score", 0),
            "res_model": "cancer.registry.qc.wizard",
            "view_mode": "form",
            "res_id": self.env["cancer.registry.qc.wizard"].create({
                "case_id": self.id,
                "score": report.get("score", 0),
                "status": report.get("status", "not_run"),
                "errors_count": report.get("errors", 0),
                "warnings_count": report.get("warnings", 0),
                "report_text": report.get("text", ""),
            }).id,
            "target": "new",
        }

    def action_preview_document(self):
        """زر «المعاينة» — يفتح المعاينة جنباً إلى جنب."""
        self.ensure_one()
        doc = self.document_ids[:1]
        if not doc:
            raise UserError(_("لا يوجد مستند لمعاينته. ارفع الملف أولاً."))
        return {
            "type": "ir.actions.act_window",
            "name": _("معاينة المستند — %s") % doc.display_name,
            "res_model": "cancer.registry.document",
            "view_mode": "form",
            "res_id": doc.id,
            "target": "new",
        }

    def action_storage_location(self):
        """زر «مكان الملف المخزن» — يفتح مجلد الأرشيف في نظام المستندات."""
        self.ensure_one()
        action = {
            "type": "ir.actions.act_window",
            "name": _("أرشيف مستندات السجل %s") % self.registry_no,
            "res_model": "cancer.registry.document",
            "view_mode": "list,form",
            "domain": [("case_id", "=", self.id)],
            "context": {"default_case_id": self.id},
        }
        # إن كانت وحدة Documents (Enterprise) مثبّتة → افتح مجلد DMS
        if self.env["ir.model"].search([("model", "=", "documents.document")], limit=1):
            folder = self.env.ref("cancer_registry.dms_folder", raise_if_not_found=False)
            if folder:
                action.update({
                    "res_model": "documents.document",
                    "domain": [("folder_id", "=", folder.id),
                               ("res_model", "=", self._name), ("res_id", "=", self.id)],
                    "context": {"default_folder_id": folder.id,
                                "default_res_model": self._name,
                                "default_res_id": self.id},
                })
        return action

    def action_export_excel(self):
        """زر «التصدير» — ملف Excel مطابق لقالب السجل الوطني."""
        self.ensure_one()
        path = pipeline.export_case(self.registry_no)
        att = self.env["ir.attachment"].create({
            "name": os.path.basename(path),
            "type": "binary",
            "datas": base64.b64encode(open(path, "rb").read()),
            "res_model": self._name,
            "res_id": self.id,
            "mimetype": "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet",
        })
        self.message_post(body=_("تم إنشاء ملف التصدير: %s") % att.name,
                          attachment_ids=[att.id])
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % att.id,
            "target": "self",
        }

    def action_validate(self):
        self.ensure_one()
        if self.qc_status == "error":
            raise UserError(_(
                "لا يمكن اعتماد سجل به أخطاء جودة.\\n"
                "شغّل «فحص جودة البيانات» وعالج الأخطاء أولاً."))
        self.write({"data_entry_status": "validated",
                    "validated_by": self.env.user.name,
                    "validated_on": fields.Date.context_today(self)})
        self.message_post(body=_("تم اعتماد السجل بواسطة %s") % self.env.user.name)

    # ------------------------------------------------- المنطق
    def _recompute_derived(self):
        """يعيد حساب الحقول المشتقة (نفس منطق الأداة المستقلة)."""
        self.ensure_one()
        vals = {}
        site = reference.normalise_site(self.primary_site or "")
        if site:
            vals["primary_site"] = site
            vals["primary_site_label"] = reference.site_label(site, "ar")
            i10 = reference.icd10_from_icdo3(site)
            if i10:
                vals["icd10_code"] = i10
        morph = reference.normalise_morphology(self.morphology or "")
        if morph:
            vals["morphology"] = morph
            vals["morphology_label"] = reference.morphology_label(morph, "ar")
            beh = reference.behaviour_from_morphology(morph)
            if beh:
                vals["behaviour"] = beh
        if not self.full_name:
            vals["full_name"] = " ".join(filter(None, [
                self.first_name, self.father_name,
                self.grandfather_name, self.family_name])).strip()
        dob, dod = self.birth_date, self.date_of_diagnosis
        if dob and dod:
            vals["age_at_diagnosis"] = (dod.year - dob.year
                                        - ((dod.month, dod.day) < (dob.month, dob.day)))
        if dod:
            vals["diagnosis_year"] = dod.year
        t = self.pt or self.ct or ""
        n = self.pn or self.cn or ""
        m = self.pm or self.cm or ""
        if t or n or m:
            sg = reference.derive_stage_group(site, t, n, m)
            if sg and not self.pathological_stage:
                vals["pathological_stage"] = sg
            ss = reference.summary_stage_from_tnm(t, n, m)
            if ss and ss != "unknown":
                vals["summary_stage"] = ss
        end = self.date_of_death or self.last_followup_date
        if dod and end and end >= dod:
            vals["survival_months"] = (end.year - dod.year) * 12 + (end.month - dod.month)
        if vals:
            self.write(vals)

    def _apply_extracted(self, record: dict) -> dict:
        """يفرّغ dict الاستخراج في السجل دون الكتابة فوق ما أدخله المستخدم."""
        self.ensure_one()
        vals = {}
        for key, value in record.items():
            if key not in self._fields or key.startswith("_"):
                continue
            fld = self._fields[key]
            if fld.readonly or fld.related or fld.type in ("one2many", "many2many", "binary"):
                continue
            current = self[key]
            if current not in (False, None, "", 0, 0.0):
                continue                      # مُدخَل يدوياً → لا نستبدله
            try:
                if fld.type == "date":
                    value = fields.Date.to_date(str(value)[:10])
                elif fld.type == "datetime":
                    value = fields.Datetime.to_datetime(value)
                elif fld.type == "selection":
                    valid = [k for k, _ in fld.selection(self)]
                    if value not in valid:
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
        return vals

    def _as_record_dict(self) -> dict:
        """يحوّل السجل إلى dict بصيغة الأداة المستقلة (لتمريره لمحرك الجودة)."""
        self.ensure_one()
        out = {}
        for name in dictionary.FIELDS:
            if name not in self._fields:
                continue
            v = self[name]
            if isinstance(v, models.BaseModel):
                out[name] = len(v) if name == "document_count" else ""
            elif isinstance(v, (fields.Date, fields.Datetime)) or hasattr(v, "isoformat"):
                out[name] = v.isoformat() if v else ""
            elif v is False:
                out[name] = ""
            else:
                out[name] = v
        out["document_count"] = len(self.document_ids)
        out["_treatments"] = [{
            "modality": t.modality, "start_date": t.start_date and t.start_date.isoformat(),
            "end_date": t.end_date and t.end_date.isoformat(), "facility": t.facility,
            "details": t.details, "cycles": t.cycles, "dose": t.dose,
            "response": t.response, "first_course": t.first_course,
        } for t in self.treatment_ids]
        return out

    def run_quality_check(self) -> dict:
        """يشغّل محرك الجودة ويخزّن النتيجة في السجل."""
        self.ensure_one()
        record = self._as_record_dict()
        dupes = set()
        if record.get("national_id") and record.get("date_of_diagnosis"):
            key = "%s|%s|%s" % (record["national_id"],
                                reference.normalise_site(record.get("primary_site") or ""),
                                record["date_of_diagnosis"])
            same = self.search([("id", "!=", self.id),
                                ("national_id", "=", record["national_id"]),
                                ("primary_site", "=", record.get("primary_site")),
                                ("date_of_diagnosis", "=", self.date_of_diagnosis)], limit=1)
            if same:
                dupes.add(key)
        report = quality.check_case(record, duplicates=dupes)
        self.write({"qc_status": report.status, "qc_score": report.score,
                    "qc_issues": report.to_text()})
        self.qc_issue_ids.unlink()
        self.env["cancer.registry.qc.issue"].create([
            {"case_id": self.id, "code": i.code, "severity": i.severity,
             "field_name": i.field, "field_label": i.field_label if hasattr(i, "field_label")
             else dictionary.label(i.field), "message": i.message, "fix": i.fix}
            for i in report.issues if i.severity != "info"])
        self.message_post(body=_(
            "فحص الجودة: %s/100 — %s خطأ، %s تحذير") % (
                report.score, len(report.errors), len(report.warnings)))
        out = report.to_dict()
        out["text"] = report.to_text()
        return out

    # ------------------------------------------------- قيود
    @api.constrains("national_id")
    def _check_national_id(self):
        for rec in self:
            nid = (rec.national_id or "").strip()
            if nid and len(nid) != 12:
                raise ValidationError(_(
                    "الرقم الوطني يجب أن يكون 12 رقماً بالضبط (الحالي: %s رقماً).") % len(nid))

    @api.constrains("primary_site")
    def _check_primary_site(self):
        for rec in self:
            if rec.primary_site and not reference.is_valid_site(rec.primary_site):
                raise ValidationError(_(
                    "رمز ICD-O-3 «%s» غير موجود في جدول المواقع.\\n"
                    "الصيغة الصحيحة من C00.0 إلى C80.9.") % rec.primary_site)

    @api.constrains("morphology")
    def _check_morphology(self):
        for rec in self:
            if rec.morphology:
                m = reference.normalise_morphology(rec.morphology)
                if not re.match(r"^\\d{4}/[0-369]$", m):
                    raise ValidationError(_(
                        "رمز الفحص النسيجي «%s» غير صالح. الصيغة: nnnn/b (مثال 8070/3).")
                        % rec.morphology)

    @api.constrains("birth_date", "date_of_diagnosis", "date_of_death",
                    "last_followup_date")
    def _check_dates(self):
        for rec in self:
            if rec.birth_date and rec.date_of_diagnosis \\
                    and rec.birth_date > rec.date_of_diagnosis:
                raise ValidationError(_(
                    "تاريخ الميلاد (%s) بعد تاريخ التشخيص (%s).")
                    % (rec.birth_date, rec.date_of_diagnosis))
            if rec.date_of_diagnosis and rec.date_of_death \\
                    and rec.date_of_death < rec.date_of_diagnosis:
                raise ValidationError(_(
                    "تاريخ الوفاة (%s) قبل تاريخ التشخيص (%s).")
                    % (rec.date_of_death, rec.date_of_diagnosis))

    @api.constrains("vitality_status", "date_of_death")
    def _check_vitality(self):
        for rec in self:
            dead = (rec.vitality_status or "").startswith("dead")
            if dead and not rec.date_of_death:
                raise ValidationError(_(
                    "الحالة «متوفى» تستلزم إدخال تاريخ الوفاة."))
            if rec.vitality_status == "alive" and rec.date_of_death:
                raise ValidationError(_(
                    "الحالة «على قيد الحياة» مع وجود تاريخ وفاة — صحّح أحدهما."))

    @api.constrains("sex", "primary_site")
    def _check_sex_site(self):
        for rec in self:
            if not (rec.sex and rec.primary_site):
                continue
            site = reference.normalise_site(rec.primary_site)
            if quality.MALE_ONLY.match(site) and rec.sex == "female":
                raise ValidationError(_(
                    "الموقع %s (%s) خاص بالذكور ولا يتوافق مع الجنس «أنثى».")
                    % (site, reference.site_label(site, "ar")))
            if quality.FEMALE_ONLY.match(site) and rec.sex == "male" \\
                    and not site.startswith("C50"):
                raise ValidationError(_(
                    "الموقع %s (%s) خاص بالإناث ولا يتوافق مع الجنس «ذكر».")
                    % (site, reference.site_label(site, "ar")))

    @api.onchange("primary_site", "morphology", "birth_date", "date_of_diagnosis",
                  "ct", "cn", "cm", "pt", "pn", "pm", "date_of_death",
                  "last_followup_date", "first_name", "father_name",
                  "grandfather_name", "family_name")
    def _onchange_recompute(self):
        for rec in self:
            rec._recompute_derived()


# --------------------------------------------------------------- المستند
class CancerRegistryDocument(models.Model):
    _name = "cancer.registry.document"
    _description = "مستند ممسوح ضوئياً مرتبط بحالة"
    _order = "uploaded_on desc, id desc"

    case_id = fields.Many2one("cancer.registry.case", string="السجل",
                              required=True, ondelete="cascade", index=True)
    registry_no = fields.Char(related="case_id.registry_no", store=True,
                              string="رقم السجل", readonly=True)
    name = fields.Char(string="اسم الملف", required=True)
    file_content = fields.Binary(string="الملف", attachment=True)
    mime_type = fields.Char(string="النوع", readonly=True)
    file_size = fields.Integer(string="الحجم (بايت)", readonly=True)
    sha256 = fields.Char(string="بصمة SHA-256", readonly=True, index=True, copy=False)
    uploaded_on = fields.Datetime(string="تاريخ الرفع", default=fields.Datetime.now,
                                  readonly=True)
    uploaded_by = fields.Many2one("res.users", string="رفعه", readonly=True,
                                  default=lambda self: self.env.user)
    doc_type = fields.Selection([
        ("pathology", "تقرير تشريح مرضي"), ("imaging", "تقرير أشعة/تصوير"),
        ("discharge", "ملخص خروج"), ("surgery", "تقرير عملية"),
        ("oncology", "تقرير علاج أورام"), ("death", "شهادة وفاة"),
        ("lab", "تحاليل مختبر"), ("notification", "استمارة تبليغ"),
        ("followup", "متابعة"), ("other", "أخرى"),
    ], string="نوع المستند", default="pathology")
    pages_count = fields.Integer(string="عدد الصفحات", readonly=True)
    extracted_text = fields.Text(string="النص المستخرج (OCR)", readonly=True)
    ocr_engine = fields.Char(string="محرك القراءة", readonly=True)
    ocr_confidence = fields.Float(string="ثقة القراءة %", digits=(5, 2), readonly=True)
    extraction_done = fields.Boolean(string="تم الاستخراج", default=False, readonly=True)
    extraction_json = fields.Text(string="نتيجة الاستخراج (JSON)", readonly=True)
    storage_path = fields.Char(string="مسار الأرشيف على القرص", readonly=True)
    archive_note = fields.Char(string="ملاحظة الأرشفة", readonly=True)

    @api.model
    def create(self, vals):
        rec = super().create(vals)
        rec._compute_file_meta()
        return rec

    def write(self, vals):
        res = super().write(vals)
        if "file_content" in vals:
            self._compute_file_meta()
        return res

    def _compute_file_meta(self):
        """يحسب الحجم والبصمة والنوع ويؤرشف على القرص."""
        import base64
        import hashlib
        import tempfile
        for rec in self:
            if not rec.file_content:
                continue
            raw = base64.b64decode(rec.file_content)
            rec.file_size = len(raw)
            rec.sha256 = hashlib.sha256(raw).hexdigest()
            suffix = os.path.splitext(rec.name or "")[1].lower() or ".bin"
            rec.mime_type = {
                ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg", ".tif": "image/tiff", ".tiff": "image/tiff",
                ".txt": "text/plain",
            }.get(suffix, "application/octet-stream")
            # أرشفة على القرص بنفس بنية الأداة المستقلة
            dup = self.search([("sha256", "=", rec.sha256), ("id", "!=", rec.id)], limit=1)
            if dup:
                rec.archive_note = _("ملف مكرر — مطابق لـ %s (%s)") % (
                    dup.name, dup.case_id.registry_no)
                continue
            try:
                year = (rec.case_id.date_of_diagnosis and
                        str(rec.case_id.date_of_diagnosis.year)) or \\
                    str(fields.Date.context_today(rec).year)
                fd, tmp = tempfile.mkstemp(suffix=suffix)
                with os.fdopen(fd, "wb") as fh:
                    fh.write(raw)
                info = storage.store_document(tmp, rec.case_id.registry_no,
                                              original_name=rec.name, year=year)
                os.unlink(tmp)
                rec.storage_path = info.get("stored_path", "")
                if info.get("duplicate"):
                    rec.archive_note = _("موجود مسبقاً في الأرشيف")
            except Exception as exc:                     # pragma: no cover
                rec.archive_note = _("تعذّرت الأرشفة: %s") % exc

    def run_extraction(self) -> dict:
        """يقرأ المستند ويستخرج الحقول — يُستدعى من زر الحالة."""
        self.ensure_one()
        import base64
        import tempfile
        if not self.file_content:
            if not self.extracted_text:
                raise UserError(_("لا يوجد ملف ولا نص في هذا المستند."))
            res = extractor.extract(self.extracted_text, engine="manual")
        else:
            suffix = os.path.splitext(self.name or "")[1] or ".pdf"
            fd, tmp = tempfile.mkstemp(suffix=suffix)
            with os.fdopen(fd, "wb") as fh:
                fh.write(base64.b64decode(self.file_content))
            try:
                out = pipeline.read_and_extract(tmp)
            finally:
                os.unlink(tmp)
            res = {
                "record": out["record"],
                "engine": out["ocr"]["engine"],
                "confidence": out["extraction"]["confidence"],
                "text": out["ocr"]["text"],
                "warnings": out["ocr"].get("warnings", []),
                "hits": out["extraction"]["hits"],
            }
        self.write({
            "extracted_text": (res.get("text") or "")[:200000],
            "ocr_engine": res.get("engine", ""),
            "ocr_confidence": res.get("confidence", 0.0),
            "extraction_done": True,
            "extraction_json": json.dumps(
                {"record": res.get("record", {}), "hits": res.get("hits", {})},
                ensure_ascii=False, default=str)[:500000],
            "pages_count": (res.get("text") or "").count("\\f") + 1,
        })
        return res

    def action_reextract(self):
        self.ensure_one()
        res = self.run_extraction()
        self.case_id.message_post(body=_(
            "إعادة استخراج من %s — %s حقل (ثقة %s%%)") % (
                self.name, len(res.get("record") or {}), res.get("confidence", 0)))

    def action_apply_to_case(self):
        """تفريغ الحقول المستخرجة في السجل (بدون تجاوز ما أُدخل يدوياً)."""
        self.ensure_one()
        if not self.extraction_json:
            raise UserError(_("شغّل الاستخراج أولاً."))
        data = json.loads(self.extraction_json)
        vals = self.case_id._apply_extracted(data.get("record") or {})
        if not vals:
            raise UserError(_("لا توجد حقول جديدة للتفريغ — السجل ممتلئ بالفعل."))
        self.case_id.write(vals)
        self.case_id._recompute_derived()
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"title": _("تم التفريغ"),
                           "message": _("أُضيف %s حقل إلى السجل.") % len(vals),
                           "type": "success"}}

    def action_storage_location(self):
        self.ensure_one()
        path = self.storage_path or _("غير مؤرشف على القرص")
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"title": _("مكان الملف المخزَّن"), "message": str(path),
                           "type": "info", "sticky": True}}


# --------------------------------------------------------------- العلاج
class CancerRegistryTreatment(models.Model):
    _name = "cancer.registry.treatment"
    _description = "سطر علاج لحالة سجل السرطان"
    _order = "start_date, id"

    case_id = fields.Many2one("cancer.registry.case", string="السجل",
                              required=True, ondelete="cascade", index=True)
    modality = fields.Selection(selection="_sel_modality", string="نوع العلاج",
                                required=True)
    start_date = fields.Date(string="تاريخ البدء")
    end_date = fields.Date(string="تاريخ الانتهاء")
    facility = fields.Char(string="الجهة المنفذة")
    details = fields.Text(string="التفاصيل / البروتوكول")
    protocol = fields.Char(string="البروتوكول")
    cycles = fields.Integer(string="عدد الدورات")
    dose = fields.Char(string="الجرعة")
    rt_type = fields.Selection(selection="_sel_rt_type", string="نوع الإشعاع")
    response = fields.Selection(selection="_sel_response", string="الاستجابة")
    first_course = fields.Boolean(
        string="ضمن الدورة الأولى (≤ 4 أشهر)",
        help="معيار SEER/IARC: علاج أُعطي خلال 4 أشهر من تاريخ التشخيص")
    physician = fields.Char(string="الطبيب المعالج")

    @api.model
    def _sel_modality(self):
        return dictionary.option_pairs("treatment_modality", self.env.lang or "ar_AR")

    @api.model
    def _sel_rt_type(self):
        return dictionary.option_pairs("radiotherapy_type", self.env.lang or "ar_AR")

    @api.model
    def _sel_response(self):
        return dictionary.option_pairs("treatment_response", self.env.lang or "ar_AR")

    @api.constrains("start_date", "end_date")
    def _check_dates(self):
        for rec in self:
            if rec.start_date and rec.end_date and rec.end_date < rec.start_date:
                raise ValidationError(_("تاريخ انتهاء العلاج قبل تاريخ البدء."))


# --------------------------------------------------------------- مشاكل الجودة
class CancerRegistryQcIssue(models.Model):
    _name = "cancer.registry.qc.issue"
    _description = "مشكلة جودة بيانات"
    _order = "severity_order, code"

    case_id = fields.Many2one("cancer.registry.case", string="السجل",
                              required=True, ondelete="cascade", index=True)
    code = fields.Char(string="رمز القاعدة")
    severity = fields.Selection([("error", "خطأ"), ("warning", "تحذير"),
                                 ("info", "ملاحظة")], string="الخطورة")
    severity_order = fields.Integer(compute="_compute_order", store=True)
    field_name = fields.Char(string="الحقل (تقني)")
    field_label = fields.Char(string="اسم الحقل")
    message = fields.Text(string="المشكلة")
    fix = fields.Text(string="الإصلاح المقترح")
    reference = fields.Char(string="المرجع المعياري")
    resolved = fields.Boolean(string="تمت المعالجة", default=False)

    @api.depends("severity")
    def _compute_order(self):
        order = {"error": 0, "warning": 1, "info": 2}
        for rec in self:
            rec.severity_order = order.get(rec.severity, 9)

    @api.model
    def create(self, vals):
        cat = quality.RULE_CATALOGUE.get(vals.get("code") or "")
        if cat and not vals.get("reference"):
            vals["reference"] = cat[3]
        return super().create(vals)
''')
    text = "".join(out)
    # استيرادات إضافية تُستخدم في الكود المولَّد
    text = text.replace("from odoo import api, fields, models, _",
                        "import base64\nimport json\nimport os\nimport re\n\n"
                        "from odoo import api, fields, models, _")
    return text


def build_bridge() -> str:
    return '''# -*- coding: utf-8 -*-
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
'''


def build_refdata_xml() -> None:
    """يولّد بيانات ICD-O-3 كملفات XML تُحمَّل عند تثبيت الوحدة."""
    data_dir = ADDON / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    with (data_dir / "icdo3_topography_data.xml").open("w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="utf-8"?>\n<odoo>\n    <data noupdate="1">\n')
        for code, row in sorted(ref.topography().items()):
            ext = (row.get("label_en") or "").replace("&", "&amp;").replace('"', "&quot;")
            ar = (row.get("label_ar") or "").replace("&", "&amp;").replace('"', "&quot;")
            sysname = (row.get("system") or "").replace("&", "&amp;")
            fh.write(
                f'        <record id="topo_{code.replace(".", "_").lower()}" '
                f'model="cancer.registry.icdo3.topography">\n'
                f'            <field name="code">{code}</field>\n'
                f'            <field name="name_en">{ext}</field>\n'
                f'            <field name="name_ar">{ar}</field>\n'
                f'            <field name="system_group">{sysname}</field>\n'
                f'        </record>\n')
        fh.write('    </data>\n</odoo>\n')

    with (data_dir / "icdo3_morphology_data.xml").open("w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="utf-8"?>\n<odoo>\n    <data noupdate="1">\n')
        for code, row in sorted(ref.morphology().items()):
            ext = (row.get("label_en") or "").replace("&", "&amp;").replace('"', "&quot;")
            ar = (row.get("label_ar") or "").replace("&", "&amp;").replace('"', "&quot;")
            xml_id = "morph_" + code.replace("/", "_").replace(".", "_").lower()
            fh.write(
                f'        <record id="{xml_id}" model="cancer.registry.icdo3.morphology">\n'
                f'            <field name="code">{code}</field>\n'
                f'            <field name="name_en">{ext}</field>\n'
                f'            <field name="name_ar">{ar}</field>\n'
                f'            <field name="behaviour">{row.get("behaviour", "3")}</field>\n'
                f'            <field name="group_name">{(row.get("group") or "").replace("&", "&amp;")}</field>\n'
                f'        </record>\n')
        fh.write('    </data>\n</odoo>\n')
    print(f"  ✓ data/icdo3_topography_data.xml  ({len(ref.topography())} رمز)")
    print(f"  ✓ data/icdo3_morphology_data.xml  ({len(ref.morphology())} رمز)")


REFMODELS = '''# -*- coding: utf-8 -*-
"""جداول ICD-O-3 المرجعية داخل أودو — تُحمَّل من data/*.xml عند التثبيت."""

from odoo import fields, models


class Icdo3Topography(models.Model):
    _name = "cancer.registry.icdo3.topography"
    _description = "ICD-O-3 Topography — مواقع الورم الأولي"
    _order = "code"
    _rec_names_search = ["code", "name_ar", "name_en"]

    code = fields.Char(string="الرمز", required=True, index=True)
    name_ar = fields.Char(string="الاسم بالعربية", translate=True)
    name_en = fields.Char(string="الاسم بالإنجليزية")
    system_group = fields.Char(string="الجهاز")

    _sql_constraints = [("code_uniq", "unique(code)", "رمز ICD-O-3 مكرر!")]


class Icdo3Morphology(models.Model):
    _name = "cancer.registry.icdo3.morphology"
    _description = "ICD-O-3 Morphology — الفحص النسيجي"
    _order = "code"
    _rec_names_search = ["code", "name_ar", "name_en"]

    code = fields.Char(string="الرمز", required=True, index=True)
    name_ar = fields.Char(string="الاسم بالعربية", translate=True)
    name_en = fields.Char(string="الاسم بالإنجليزية")
    behaviour = fields.Selection([
        ("0", "/0 حميد"), ("1", "/1 سلوك غير مؤكد"), ("2", "/2 لابِد"),
        ("3", "/3 خبيث أولي"), ("6", "/6 خبيث ثانوي"), ("9", "/9 خبيث غير محدد"),
    ], string="السلوك")
    group_name = fields.Char(string="المجموعة")

    _sql_constraints = [("code_uniq", "unique(code)", "رمز الفحص النسيجي مكرر!")]
'''


def build_access_csv() -> None:
    sec = ADDON / "security"
    sec.mkdir(parents=True, exist_ok=True)
    models = [
        ("cancer_registry_case", "cancer.registry.case"),
        ("cancer_registry_document", "cancer.registry.document"),
        ("cancer_registry_treatment", "cancer.registry.treatment"),
        ("cancer_registry_qc_issue", "cancer.registry.qc.issue"),
        ("icdo3_topography", "cancer.registry.icdo3.topography"),
        ("icdo3_morphology", "cancer.registry.icdo3.morphology"),
    ]
    groups = ["group_registry_user", "group_registry_manager"]
    lines = ["id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink"]
    for slug, model in models:
        mid = f"model_{model.replace('.', '_')}"
        # المستخدم: قراءة/كتابة/إنشاء — بدون حذف للجداول المرجعية والسجلات
        ref_table = model.startswith("cancer.registry.icdo3")
        lines.append(f"access_{slug}_user,{model} user,{mid},"
                     f"cancer_registry.{groups[0]},1,{0 if ref_table else 1},"
                     f"{0 if ref_table else 1},0")
        lines.append(f"access_{slug}_manager,{model} manager,{mid},"
                     f"cancer_registry.{groups[1]},1,1,1,1")
    for slug, model in [("extract_wizard", "cancer.registry.extract.wizard"),
                        ("qc_wizard", "cancer.registry.qc.wizard"),
                        ("qc_rules_wizard", "cancer.registry.qc.rules.wizard"),
                        ("export_wizard", "cancer.registry.export.wizard")]:
        mid = "model_" + model.replace(".", "_")
        lines.append(f"access_{slug}_user,{model}.user,"
                     f"{mid},cancer_registry.{groups[0]},1,1,1,1")
    (sec / "ir.model.access.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  ✓ security/ir.model.access.csv ({len(lines)-1} قاعدة)")


def main():
    print("بناء وحدة أودو من قاموس الحقول…\n")
    ADDON.mkdir(parents=True, exist_ok=True)
    (ADDON / "models").mkdir(exist_ok=True)
    (ADDON / "views").mkdir(exist_ok=True)
    (ADDON / "wizards").mkdir(exist_ok=True)

    # 1) نسخ النواة داخل الوحدة
    dest_core = ADDON / "crcore"
    if dest_core.exists():
        shutil.rmtree(dest_core)
    shutil.copytree(CORE, dest_core,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    print(f"  ✓ crcore/ → odoo/cancer_registry/crcore/ ({len(list(dest_core.rglob('*.py')))} ملف بايثون)")

    # 2) إضافة option_pairs إلى القاموس (يحتاجها أودو للقوائم المترجمة)
    dict_py = dest_core / "dictionary.py"
    s = dict_py.read_text(encoding="utf-8")
    if "def option_pairs" not in s:
        s = s.replace('''def option_values(field_name):''', '''def option_pairs(field_name, lang="ar_AR"):
    """[(key, label)] بلغة أودو — تُستخدم في Selection fields."""
    ar = not lang.startswith("en")
    f = FIELDS.get(field_name)
    if not f or not f["options"]:
        return []
    return [(k, (v[0] if ar else v[1])) for k, v in f["options"].items()]


def option_values(field_name):''')
        dict_py.write_text(s, encoding="utf-8")
        print("  ✓ dictionary.option_pairs() أُضيفت للنسخة المضمّنة")
    # ونفس الشىء للنسخة الأصلية
    src_dict = CORE / "dictionary.py"
    t = src_dict.read_text(encoding="utf-8")
    if "def option_pairs" not in t:
        t = t.replace('''def option_values(field_name):''', '''def option_pairs(field_name, lang="ar_AR"):
    """[(key, label)] بلغة أودو — تُستخدم في Selection fields."""
    ar = not lang.startswith("en")
    f = FIELDS.get(field_name)
    if not f or not f["options"]:
        return []
    return [(k, (v[0] if ar else v[1])) for k, v in f["options"].items()]


def option_values(field_name):''')
        src_dict.write_text(t, encoding="utf-8")
        print("  ✓ dictionary.option_pairs() أُضيفت للنسخة الأصلية")

    # 3) توليد الملفات
    (ADDON / "models" / "cr_bridge.py").write_text(build_bridge(), encoding="utf-8")
    print("  ✓ models/cr_bridge.py")

    (ADDON / "models" / "refdata_models.py").write_text(REFMODELS, encoding="utf-8")
    print("  ✓ models/refdata_models.py")

    (ADDON / "models" / "cancer_registry.py").write_text(build_model(), encoding="utf-8")
    n_fields = sum(1 for f in dic.DATA_DICTIONARY if f["type"] != "one2many")
    print(f"  ✓ models/cancer_registry.py  ({n_fields} حقل من القاموس)")

    build_refdata_xml()
    build_access_csv()
    print("\n✓ اكتمل البناء. ثبّت الوحدة من: Settings → Apps → Update Apps List")


if __name__ == "__main__":
    main()

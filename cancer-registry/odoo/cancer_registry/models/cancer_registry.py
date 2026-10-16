# -*- coding: utf-8 -*-
# =============================================================================
#  هذا الملف مُولَّد آلياً من crcore/dictionary.py
#  للتجديد:   python3 tools/build_odoo_addon.py
#  لا تعدّل الحقول هنا يدوياً — عدّل القاموس ثم أعد التوليد، فتتطابق
#  وحدة أودو مع الأداة المستقلة ومع ملف Excel المُصدَّر.
# =============================================================================
import base64
import json
import os
import re

from odoo import api, fields, models, _
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
    # ═══ A. Identifiers ═══
    national_id = fields.Char(string="الرقم الوطني", size=128, required=True, help=r"12 رقماً — يُستخدم لمنع التكرار بين السجلات — الصيغة المقبولة: ^\d{12}$")
    medical_file_no = fields.Char(string="رقم الملف الطبي", size=128, help=r"رقم الملف في المستشفى المبلِّغ")
    reporting_facility = fields.Char(string="الجهة المبلِّغة", size=128, required=True, help=r"اسم المستشفى/المركز الذي ورد منه التبليغ")
    reporter_name = fields.Char(string="اسم المبلِّغ", size=128)
    notification_date = fields.Date(string="تاريخ التبليغ")

    # ═══ B. Demographics ═══
    first_name = fields.Char(string="الاسم الأول", size=128, required=True)
    father_name = fields.Char(string="اسم الأب", size=128, required=True)
    grandfather_name = fields.Char(string="اسم الجد", size=128)
    family_name = fields.Char(string="اسم العائلة / اللقب", size=128, required=True)
    full_name = fields.Char(string="الاسم الكامل", size=128, help=r"يُحسب تلقائياً من الرباعي — قابل للتعديل")
    sex = fields.Selection(selection="_sel_sex", string="الجنس", required=True, tracking=True)
    birth_date = fields.Date(string="تاريخ الميلاد", required=True, help=r"إن كان مجهولاً يُستخدم 01-01 من السنة")
    birth_date_known = fields.Boolean(string="تاريخ الميلاد معروف بدقة", help=r"إن كان غير معروف → السنة التقديرية فقط")
    age_at_diagnosis = fields.Integer(string="العمر عند التشخيص", help=r"يُحسب تلقائياً = تاريخ التشخيص − تاريخ الميلاد")
    district = fields.Selection(selection="_sel_district", string="البلدية", required=True, tracking=True)
    city = fields.Char(string="المدينة / المحلة", size=128)
    address = fields.Text(string="العنوان التفصيلي", translate=False)
    phone = fields.Char(string="رقم الهاتف", size=128, help=r"الصيغة المقبولة: ^[0-9+\-\s]{7,20}$")

    # ═══ C. Diagnosis & Tumour ═══
    date_of_diagnosis = fields.Date(string="تاريخ أول تشخيص", required=True, help=r"أول تاريخ أثبت فيه الورم نسيجياً أو سريريّاً")
    date_of_first_symptom = fields.Date(string="تاريخ أول عرض")
    diagnosis_year = fields.Integer(string="سنة التشخيص", help=r"يُحسب تلقائياً من تاريخ التشخيص")
    basis_of_diagnosis = fields.Selection(selection="_sel_basis_of_diagnosis", string="أساس التشخيص", required=True, tracking=True)
    primary_site = fields.Char(string="موقع الورم الأولي (ICD-O-3)", size=128, required=True, help=r"C00.0 – C80.9 — الصيغة المقبولة: ^C\d{2}(\.\d{1,2})?$ — المرجع: ICD-O-3 Topography")
    primary_site_label = fields.Char(string="اسم الموقع الأولي", size=128, help=r"يُعبّأ تلقائياً من جدول ICD-O-3")
    icd10_code = fields.Char(string="ترميز ICD-10", size=128, help=r"C00-D49 — يُشتق تلقائياً من ICD-O-3 عندما يكون ممكناً — الصيغة المقبولة: ^[CD]\d{2}(\.\d{1,2})?$ — المرجع: ICD-10 Chapter II")
    laterality = fields.Selection(selection="_sel_laterality", string="الجانبية")
    morphology = fields.Char(string="الفحص النسيجي (Morphology)", size=128, required=True, help=r"مثال: 8070/3 سرطانة حرشفية — الصيغة المقبولة: ^\d{4}/[0-369]$ — المرجع: ICD-O-3 Morphology")
    morphology_label = fields.Char(string="اسم النسيج المرضي", size=128, help=r"يُعبّأ تلقائياً من جدول ICD-O-3")
    behaviour = fields.Selection(selection="_sel_behaviour", string="السلوك (Behaviour)")
    histology_text = fields.Text(string="نص التشخيص النسيجي (حرفي)", translate=False, help=r"نص التشخيص كما ورد في تقرير التشريح المرضي — للمراجعة البشرية")
    grade = fields.Selection(selection="_sel_grade", string="درجة التمايز")
    multiple_primaries = fields.Boolean(string="أورام أولية متعددة", help=r"أكثر من ورم أولي مستقل في نفس المريض")
    primary_count = fields.Integer(string="عدد الأورام الأولية")
    family_history = fields.Text(string="تاريخ عائلي للسرطان", translate=False)
    risk_factors = fields.Text(string="عوامل الخطورة", translate=False, help=r"تدخين، التهاب كبدي B/C، HPV، سمنة، تعرّض مهني…")

    # ═══ D. Staging (TNM) ═══
    staging_system = fields.Selection(selection="_sel_staging_system", string="نظام التقسيم المرحلي")
    ct = fields.Selection(selection="_sel_ct", string="cT (سريري)")
    cn = fields.Selection(selection="_sel_cn", string="cN (سريري)")
    cm = fields.Selection(selection="_sel_cm", string="cM (سريري)")
    clinical_stage = fields.Selection(selection="_sel_clinical_stage", string="المرحلة السريرية")
    pt = fields.Selection(selection="_sel_pt", string="pT (نسيجي)")
    pn = fields.Selection(selection="_sel_pn", string="pN (نسيجي)")
    pm = fields.Selection(selection="_sel_pm", string="pM (نسيجي)")
    pathological_stage = fields.Selection(selection="_sel_pathological_stage", string="المرحلة النسيجية")
    summary_stage = fields.Selection(selection="_sel_summary_stage", string="المرحلة الموجزة (SEER)", tracking=True)
    stage_date = fields.Date(string="تاريخ تحديد المرحلة")
    metastasis_sites = fields.Text(string="مواقع الانتشار", translate=False)
    biomarkers = fields.Text(string="المؤشرات الحيوية", translate=False)

    # ═══ E. Treatment ═══
    first_course_within_4m = fields.Boolean(string="العلاج الأول خلال 4 أشهر", help=r"معيار SEER/IARC: أي علاج أُعطي خلال 4 أشهر من التشخيص")
    treatment_centre = fields.Selection(selection="_sel_treatment_centre", string="مركز العلاج الرئيسي")
    treatment_summary = fields.Text(string="ملخص العلاج", translate=False)
    chemo_cycles = fields.Integer(string="عدد دورات العلاج الكيميائي")
    chemo_protocol = fields.Char(string="بروتوكول العلاج الكيميائي", size=128, help=r"مثال: FOLFOX-4، AC→T، CHOP، R-CHOP")
    radiotherapy_type = fields.Selection(selection="_sel_radiotherapy_type", string="نوع العلاج الإشعاعي")
    radiotherapy_dose = fields.Char(string="الجرعة الإشعاعية الكلية (Gy)", size=128, help=r"مثال: 50 Gy / 25 جلسة")
    surgery_procedure = fields.Char(string="نوع العملية الجراحية", size=200)
    treatment_response = fields.Selection(selection="_sel_treatment_response", string="الاستجابة للعلاج")
    surgery_performed = fields.Boolean(string="أُجريت جراحة")
    chemotherapy_given = fields.Boolean(string="أُعطي علاج كيميائي")
    radiotherapy_given = fields.Boolean(string="أُعطي علاج إشعاعي")
    hormonal_given = fields.Boolean(string="أُعطي علاج هرموني")
    immunotherapy_given = fields.Boolean(string="أُعطي علاج مناعي/موجّه")

    # ═══ F. Follow-up & Outcome ═══
    vitality_status = fields.Selection(selection="_sel_vitality_status", string="حالة الحالة", required=True, tracking=True)
    date_of_death = fields.Date(string="تاريخ الوفاة", help=r"إلزامي إذا كانت الحالة = متوفى")
    cause_of_death = fields.Selection(selection="_sel_cause_of_death", string="سبب الوفاة")
    cause_of_death_icd10 = fields.Char(string="رمز ICD-10 لسبب الوفاة", size=128, help=r"الصيغة المقبولة: ^[A-Z]\d{2}(\.\d{1,2})?$")
    death_age = fields.Integer(string="العمر عند الوفاة")
    survival_months = fields.Integer(string="مدة البقاء (بالأشهر)", help=r"يُحسب = (تاريخ الوفاة أو آخر متابعة) − تاريخ التشخيص")
    last_followup_date = fields.Date(string="تاريخ آخر متابعة")
    last_disease_status = fields.Selection(selection="_sel_last_disease_status", string="حالة المرض عند آخر متابعة")
    followup_source = fields.Char(string="مصدر معلومات المتابعة", size=128, help=r"سجل مدني، اتصال هاتفي، زيارة منزلية…")
    recurrence = fields.Boolean(string="حدوث انتكاسة")
    recurrence_date = fields.Date(string="تاريخ الانتكاسة")

    # ═══ G. Documents & Audit ═══
    document_ids = fields.One2many("cancer.registry.document", "case_id", string="المستندات المرفقة")
    document_count = fields.Integer(string="عدد المستندات")
    extraction_method = fields.Char(string="طريقة الاستخراج", size=128)
    extraction_confidence = fields.Float(string="ثقة الاستخراج (%)", digits=(5, 2))
    qc_status = fields.Selection(selection="_sel_qc_status", string="حالة جودة البيانات", tracking=True)
    qc_score = fields.Integer(string="نقاط الجودة (0-100)")
    qc_issues = fields.Text(string="ملاحظات الجودة", translate=False)
    data_entry_status = fields.Selection(selection="_sel_data_entry_status", string="حالة إدخال البيانات", tracking=True)
    validated_by = fields.Char(string="اعتمده", size=128)
    validated_on = fields.Date(string="تاريخ الاعتماد")

    # ------------------------------------------------- حقول إضافية خاصة بأودو
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
    @api.model
    def _sel_sex(self):
        return dictionary.option_pairs("sex", self.env.lang or "ar_AR")

    @api.model
    def _sel_district(self):
        return dictionary.option_pairs("district", self.env.lang or "ar_AR")

    @api.model
    def _sel_basis_of_diagnosis(self):
        return dictionary.option_pairs("basis_of_diagnosis", self.env.lang or "ar_AR")

    @api.model
    def _sel_laterality(self):
        return dictionary.option_pairs("laterality", self.env.lang or "ar_AR")

    @api.model
    def _sel_behaviour(self):
        return dictionary.option_pairs("behaviour", self.env.lang or "ar_AR")

    @api.model
    def _sel_grade(self):
        return dictionary.option_pairs("grade", self.env.lang or "ar_AR")

    @api.model
    def _sel_staging_system(self):
        return dictionary.option_pairs("staging_system", self.env.lang or "ar_AR")

    @api.model
    def _sel_ct(self):
        return dictionary.option_pairs("ct", self.env.lang or "ar_AR")

    @api.model
    def _sel_cn(self):
        return dictionary.option_pairs("cn", self.env.lang or "ar_AR")

    @api.model
    def _sel_cm(self):
        return dictionary.option_pairs("cm", self.env.lang or "ar_AR")

    @api.model
    def _sel_clinical_stage(self):
        return dictionary.option_pairs("clinical_stage", self.env.lang or "ar_AR")

    @api.model
    def _sel_pt(self):
        return dictionary.option_pairs("pt", self.env.lang or "ar_AR")

    @api.model
    def _sel_pn(self):
        return dictionary.option_pairs("pn", self.env.lang or "ar_AR")

    @api.model
    def _sel_pm(self):
        return dictionary.option_pairs("pm", self.env.lang or "ar_AR")

    @api.model
    def _sel_pathological_stage(self):
        return dictionary.option_pairs("pathological_stage", self.env.lang or "ar_AR")

    @api.model
    def _sel_summary_stage(self):
        return dictionary.option_pairs("summary_stage", self.env.lang or "ar_AR")

    @api.model
    def _sel_treatment_centre(self):
        return dictionary.option_pairs("treatment_centre", self.env.lang or "ar_AR")

    @api.model
    def _sel_radiotherapy_type(self):
        return dictionary.option_pairs("radiotherapy_type", self.env.lang or "ar_AR")

    @api.model
    def _sel_treatment_response(self):
        return dictionary.option_pairs("treatment_response", self.env.lang or "ar_AR")

    @api.model
    def _sel_vitality_status(self):
        return dictionary.option_pairs("vitality_status", self.env.lang or "ar_AR")

    @api.model
    def _sel_cause_of_death(self):
        return dictionary.option_pairs("cause_of_death", self.env.lang or "ar_AR")

    @api.model
    def _sel_last_disease_status(self):
        return dictionary.option_pairs("last_disease_status", self.env.lang or "ar_AR")

    @api.model
    def _sel_qc_status(self):
        return dictionary.option_pairs("qc_status", self.env.lang or "ar_AR")

    @api.model
    def _sel_data_entry_status(self):
        return dictionary.option_pairs("data_entry_status", self.env.lang or "ar_AR")

    # ------------------------------------------------- الأزرار والإجراءات
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
                "لا يوجد مستند مرفق بهذه الحالة.\n"
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
            msg += "\n" + "\n".join("• " + w for w in warnings[:6])
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
                "لا يمكن اعتماد سجل به أخطاء جودة.\n"
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
                    "رمز ICD-O-3 «%s» غير موجود في جدول المواقع.\n"
                    "الصيغة الصحيحة من C00.0 إلى C80.9.") % rec.primary_site)

    @api.constrains("morphology")
    def _check_morphology(self):
        for rec in self:
            if rec.morphology:
                m = reference.normalise_morphology(rec.morphology)
                if not re.match(r"^\d{4}/[0-369]$", m):
                    raise ValidationError(_(
                        "رمز الفحص النسيجي «%s» غير صالح. الصيغة: nnnn/b (مثال 8070/3).")
                        % rec.morphology)

    @api.constrains("birth_date", "date_of_diagnosis", "date_of_death",
                    "last_followup_date")
    def _check_dates(self):
        for rec in self:
            if rec.birth_date and rec.date_of_diagnosis \
                    and rec.birth_date > rec.date_of_diagnosis:
                raise ValidationError(_(
                    "تاريخ الميلاد (%s) بعد تاريخ التشخيص (%s).")
                    % (rec.birth_date, rec.date_of_diagnosis))
            if rec.date_of_diagnosis and rec.date_of_death \
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
            if quality.FEMALE_ONLY.match(site) and rec.sex == "male" \
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
                        str(rec.case_id.date_of_diagnosis.year)) or \
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
            "pages_count": (res.get("text") or "").count("\f") + 1,
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

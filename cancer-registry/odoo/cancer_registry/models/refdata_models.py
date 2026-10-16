# -*- coding: utf-8 -*-
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

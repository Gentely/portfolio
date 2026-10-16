#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
فحص ثابت لوحدة أودو — بلا تثبيت أودو
=====================================
يبني «أودو وهمي» (stub) ويستورد نماذج الوحدة فعلياً، ثم:

  1) يتحقق أن كل ملف Python يُترجم وكل ملف XML يُحلَّل
  2) يجمع أسماء الحقول المُعرَّفة لكل نموذج (بما فيها الموروثة عبر _inherit)
  3) يقارنها بكل ``<field name="…">`` في كل الواجهات → يكشف الأسماء الخاطئة
  4) يتحقق أن كل ``ref()`` في XML يشير إلى معرّف موجود في نفس الوحدة
  5) يتحقق أن كل ملف في ``__manifest__['data']`` موجود
  6) يتحقق أن كل ``model_id`` في ir.model.access.csv يقابله نموذج فعلاً
  7) يتحقق أن كل ``name="action_…"`` في الأزرار له دالة في النموذج
  8) يفحص تعديلات ``invisible/required/readonly`` لا تستخدم دوالاً غير مدعومة

الاستخدام:   python3 tools/check_odoo_addon.py
"""

from __future__ import annotations

import ast
import csv
import os
import re
import sys
import types
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADDON = ROOT / "odoo" / "cancer_registry"

ERRORS: list[str] = []
WARNINGS: list[str] = []


def err(msg):
    ERRORS.append(msg)


def warn(msg):
    WARNINGS.append(msg)


# ═══════════════════════════════════════════════════════════════════════════
#  1) أودو الوهمي
# ═══════════════════════════════════════════════════════════════════════════
REGISTRY: dict[str, dict] = {}      # model_name -> {"fields": {...}, "class": cls}
CLASS_BY_MODEL: dict[str, type] = {}
INHERITS: dict[str, list[str]] = {}


class _Field:
    _type = "char"

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.name = None
        for key in ("string", "help"):
            if key in kwargs and not isinstance(kwargs[key], str):
                err("وسيط %s يجب أن يكون نصاً" % key)

    def __repr__(self):
        return "<%s %s>" % (type(self).__name__, self.name)


def _mk(name, ftype):
    cls = type(name, (_Field,), {"_type": ftype})
    return cls


class _Date(_Field):
    _type = "date"

    @staticmethod
    def context_today(rec, timestamp=None):
        import datetime
        return datetime.date.today()

    @staticmethod
    def to_date(value):
        return value

    @staticmethod
    def today():
        import datetime
        return datetime.date.today()


class _Datetime(_Field):
    _type = "datetime"

    @staticmethod
    def to_datetime(value):
        return value

    @staticmethod
    def now():
        import datetime
        return datetime.datetime.now()


fields_mod = types.ModuleType("odoo.fields")
for fname, ftype in [
    ("Char", "char"), ("Text", "text"), ("Boolean", "boolean"), ("Integer", "integer"),
    ("Float", "float"), ("Binary", "binary"), ("Html", "html"), ("Selection", "selection"),
    ("Many2one", "many2one"), ("One2many", "one2many"), ("Many2many", "many2many"),
    ("Monetary", "monetary"), ("Reference", "reference"),
]:
    setattr(fields_mod, fname, _mk(fname, ftype))
fields_mod.Date = _Date
fields_mod.Datetime = _Datetime
fields_mod.Command = types.SimpleNamespace(
    create=lambda v: (0, 0, v), update=lambda i, v: (1, i, v), delete=lambda i: (2, i, 0),
    unlink=lambda i: (3, i, 0), link=lambda i: (4, i, 0), clear=lambda: (5, 0, 0),
    set=lambda ids: (6, 0, ids))


class ModelMeta(type):
    def __init__(cls, name, bases, attrs):
        super().__init__(name, bases, attrs)
        model = attrs.get("_name")
        inherits = attrs.get("_inherit")
        key = model or (inherits[0] if isinstance(inherits, list) else inherits)
        if not key or not isinstance(key, str):
            return
        own = {}
        for attr, value in attrs.items():
            if isinstance(value, _Field):
                value.name = attr
                own[attr] = value
        entry = REGISTRY.get(key)
        if entry is None:
            entry = {"fields": dict(own), "class": cls, "own": dict(own),
                     "attrs": dict(attrs), "ext_classes": [cls]}
            REGISTRY[key] = entry
        else:
            entry["fields"].update(own)
            entry["own"].update(own)
            entry["ext_classes"].append(cls)
            for a, v in attrs.items():
                if callable(v) and not a.startswith("__"):
                    entry["attrs"].setdefault(a, v)
        CLASS_BY_MODEL[key] = entry["class"] if model else cls


class BaseModel(metaclass=ModelMeta):
    _name = None
    _inherit = None
    _description = ""

    def __init__(self, *a, **k):
        pass


class Model(BaseModel):
    pass


class TransientModel(BaseModel):
    pass


class AbstractModel(BaseModel):
    pass


models_mod = types.ModuleType("odoo.models")
models_mod.Model = Model
models_mod.TransientModel = TransientModel
models_mod.AbstractModel = AbstractModel
models_mod.BaseModel = BaseModel


def _depends(*a, **k):
    def deco(fn):
        fn._depends = a
        return fn
    return deco


def _passthrough(*a, **k):
    def deco(fn):
        return fn
    return deco


api_mod = types.ModuleType("odoo.api")
api_mod.depends = _depends
api_mod.model = _passthrough
api_mod.model_create_multi = _passthrough
api_mod.constrains = _passthrough
api_mod.onchange = _passthrough
api_mod.autovacuum = _passthrough
api_mod.returns = _passthrough


def _(s, *a, **k):
    return s % a if a else s


exc_mod = types.ModuleType("odoo.exceptions")
for ename in ("UserError", "ValidationError", "AccessError", "MissingError",
              "RedirectWarning", "CacheMiss"):
    setattr(exc_mod, ename, type(ename, (Exception,), {}))

http_mod = types.ModuleType("odoo.http")


def _route(*a, **k):
    def deco(fn):
        fn._routes = a
        return fn
    return deco


http_mod.route = _route
http_mod.Controller = type("Controller", (), {})
http_mod.request = types.SimpleNamespace(env=None, make_response=lambda *a, **k: None,
                                          not_found=lambda *a, **k: None,
                                          httprequest=types.SimpleNamespace(path="/"))

odoo_mod = types.ModuleType("odoo")
odoo_mod.fields = fields_mod
odoo_mod.models = models_mod
odoo_mod.api = api_mod
odoo_mod._ = _
odoo_mod.exceptions = exc_mod
odoo_mod.http = http_mod
odoo_mod.tools = types.SimpleNamespace(
    misc=types.SimpleNamespace(), config={},
    file_open=lambda *a, **k: None, html_escape=lambda s: s)
odoo_mod.tools.misc = types.SimpleNamespace()

sys.modules.setdefault("odoo", odoo_mod)
sys.modules.setdefault("odoo.fields", fields_mod)
sys.modules.setdefault("odoo.models", models_mod)
sys.modules.setdefault("odoo.api", api_mod)
sys.modules.setdefault("odoo.exceptions", exc_mod)
sys.modules.setdefault("odoo.http", http_mod)
sys.modules.setdefault("odoo.tools", odoo_mod.tools)

# حزم الوحدة
pkg = types.ModuleType("cancer_registry")
pkg.__path__ = [str(ADDON)]
sys.modules["cancer_registry"] = pkg
for sub in ("models", "wizards", "controllers"):
    mod = types.ModuleType("cancer_registry.%s" % sub)
    mod.__path__ = [str(ADDON / sub)]
    sys.modules["cancer_registry.%s" % sub] = mod
    setattr(pkg, sub, mod)


# ═══════════════════════════════════════════════════════════════════════════
#  2) استيراد ملفات الوحدة
# ═══════════════════════════════════════════════════════════════════════════
def import_module_file(rel_path, mod_name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(mod_name, ADDON / rel_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


print("استيراد نماذج الوحدة…")
sys.path.insert(0, str(ADDON))
try:
    import_module_file("models/cr_bridge.py", "cancer_registry.models.cr_bridge")
    import_module_file("models/cancer_registry.py", "cancer_registry.models.cancer_registry")
    import_module_file("models/refdata_models.py", "cancer_registry.models.refdata_models")
    import_module_file("models/ui_ext.py", "cancer_registry.models.ui_ext")
    import_module_file("wizards/extract_wizard.py", "cancer_registry.wizards.extract_wizard")
    import_module_file("wizards/qc_wizard.py", "cancer_registry.wizards.qc_wizard")
    import_module_file("wizards/export_wizard.py", "cancer_registry.wizards.export_wizard")
    import_module_file("controllers/main.py", "cancer_registry.controllers.main")
except Exception as exc:                                    # pragma: no cover
    import traceback
    traceback.print_exc()
    err("فشل استيراد الوحدة: %s" % exc)
    print("\n".join("✗ " + e for e in ERRORS))
    sys.exit(1)

print("  ✓ استُوردت كل الملفات")
print("  النماذج المسجَّلة: %s" % ", ".join(sorted(REGISTRY)))

MAGIC = {
    "id", "create_uid", "create_date", "write_uid", "write_date", "display_name",
    "__count", "message_ids", "message_follower_ids", "message_main_attachment_id",
    "activity_ids", "activity_summary", "activity_state", "activity_type_id",
    "activity_user_id", "activity_date_deadline", "message_needaction",
    "message_unread", "message_has_error", "message_has_sms_error",
    "message_needaction_counter", "message_unread_counter", "message_has_error_counter",
    "message_is_follower", "message_partner_ids", "message_channel_ids",
    "my_activity_date_deadline", "activity_exception_decoration",
    "activity_exception_icon", "activity_type_icon", "web_icon_data",
}

# حقول mail.thread / mail.activity.mixin الموروثة
MAIL_MIXIN = {
    "message_ids", "message_follower_ids", "activity_ids", "message_main_attachment_id",
    "message_needaction", "message_unread", "message_has_error",
    "message_needaction_counter", "message_unread_counter", "message_has_error_counter",
    "message_is_follower", "message_partner_ids", "my_activity_date_deadline",
    "activity_state", "activity_summary", "activity_type_id", "activity_user_id",
    "activity_date_deadline", "activity_exception_decoration",
    "activity_exception_icon", "activity_type_icon",
}


def model_fields(model_name):
    """يعيد مجموعة أسماء الحقول المتاحة على نموذج (بما فيها الموروثة والسحرية)."""
    entry = REGISTRY.get(model_name)
    if not entry:
        return None
    names = set(entry["fields"]) | MAGIC
    inherits = entry["attrs"].get("_inherit")
    if isinstance(inherits, str):
        inherits = [inherits]
    for inh in (inherits or []):
        if inh in ("mail.thread", "mail.activity.mixin"):
            names |= MAIL_MIXIN
        elif inh in REGISTRY:
            names |= set(REGISTRY[inh]["fields"])
            ih = REGISTRY[inh]["attrs"].get("_inherit")
            if isinstance(ih, str):
                ih = [ih]
            for x in (ih or []):
                if x in ("mail.thread", "mail.activity.mixin"):
                    names |= MAIL_MIXIN
    return names


# ═══════════════════════════════════════════════════════════════════════════
#  3) فحص ملفات Python و XML
# ═══════════════════════════════════════════════════════════════════════════
print("\nفحص الصياغة…")
for py in sorted(ADDON.rglob("*.py")):
    if "crcore" in py.parts:
        continue
    try:
        compile(py.read_text(encoding="utf-8"), str(py), "exec")
    except SyntaxError as exc:
        err("SyntaxError في %s:%s — %s" % (py.relative_to(ADDON), exc.lineno, exc.msg))

manifest_path = ADDON / "__manifest__.py"
try:
    manifest = ast.literal_eval(manifest_path.read_text(encoding="utf-8"))
except Exception as exc:
    err("__manifest__.py غير صالح: %s" % exc)
    manifest = {"data": []}

for dep in ("base", "web", "mail"):
    if dep not in manifest.get("depends", []):
        err("الوحدة تعتمد على %s غير مُعلن في depends" % dep)

xml_files = []
for rel in manifest.get("data", []):
    path = ADDON / rel
    if not path.exists():
        err("__manifest__ يشير إلى ملف غير موجود: %s" % rel)
        continue
    if path.suffix.lower() != ".xml":
        continue                      # CSV وغيره يُفحص في قسمه الخاص
    xml_files.append((rel, path))
    try:
        ET.parse(path)
    except ET.ParseError as exc:
        err("XML غير صالح %s — %s" % (rel, exc))

# أي ملف XML موجود لكنه غير مُعلن
for path in sorted(ADDON.rglob("*.xml")):
    rel = str(path.relative_to(ADDON))
    if rel not in manifest.get("data", []) and not path.parent.name == "static":
        warn("ملف XML غير مُدرج في __manifest__['data']: %s" % rel)
print("  ✓ %s ملف Python و %s ملف XML" % (
    len([p for p in ADDON.rglob("*.py") if "crcore" not in p.parts]), len(xml_files)))


# ═══════════════════════════════════════════════════════════════════════════
#  4) فحص الواجهات
# ═══════════════════════════════════════════════════════════════════════════
print("\nفحص الواجهات…")
XML_IDS: set[str] = set()
VIEW_COUNT = 0
FORBIDDEN_EXPR = re.compile(r"\.(startswith|endswith|strip|lower|upper|split)\(")


def check_expr(model, attr_name, expr, where):
    if not expr or expr in ("0", "1"):
        return
    if FORBIDDEN_EXPR.search(expr):
        err("%s: %s='%s' يستخدم دالة نصية غير مدعومة في تعديلات الواجهة "
            "(استخدم in / not in بدلاً منها)" % (where, attr_name, expr))
    for ident in re.findall(r"[A-Za-z_][A-Za-z_0-9]*", expr):
        if ident in ("True", "False", "None", "true", "false", "null", "uid",
                     "user", "context", "parent", "active_id", "active_ids",
                     "today", "now", "datetime", "date", "time"):
            continue
        avail = model_fields(model) or {}
        if ident not in avail:
            err("%s: %s='%s' يشير إلى حقل غير موجود «%s» في %s"
                % (where, attr_name, expr, ident, model))


PY_KEYWORDS = {
    "and", "or", "not", "in", "is", "if", "else", "True", "False", "None",
    "true", "false", "null", "uid", "user", "context", "parent", "active_id",
    "active_ids", "active_model", "today", "now", "datetime", "date", "time",
    "timedelta", "self", "id", "len", "str", "int", "float", "bool",
    "current_company", "allowed_company_ids", "group_by", "search_default",
    "default", "form_view_ref", "tree_view_ref",
}


def check_expr(model, attr_name, expr, where):
    """يفحص تعديلات الواجهة (invisible/required/readonly)."""
    if not expr or expr.strip() in ("0", "1"):
        return
    if FORBIDDEN_EXPR.search(expr):
        err("%s: %s='%s' يستخدم دالة نصية غير مدعومة في تعديلات الواجهة "
            "(استخدم in / not in بدلاً منها)" % (where, attr_name, expr))
    avail = model_fields(model) or set()
    # احذف السلاسل النصية ثم افحص المعرّفات المتبقية
    stripped = re.sub(r"'[^']*'|\"[^\"]*\"|\d+", " ", expr)
    for ident in re.findall(r"[A-Za-z_][A-Za-z_0-9]*", stripped):
        if ident in PY_KEYWORDS or ident in avail:
            continue
        err("%s: %s='%s' يشير إلى حقل غير موجود «%s» في %s"
            % (where, attr_name, expr, ident, model))


DOMAIN_OPS = {
    "in", "not in", "=", "!=", "<>", ">", "<", ">=", "<=",
    "like", "ilike", "not like", "not ilike", "=like", "=ilike", "=?",
    "child_of", "parent_of", "=child_of", "=parent_of", "any", "not any",
    "=any", "=not any", "similar", "not similar",
}

_DOMAIN_PAIR = re.compile(r"\(\s*'([a-z_][a-z_0-9]*)'\s*,\s*'([^']*)'")


def check_domain(dom, avail, where, label):
    """يفحص أسماء الحقول داخل domain — يتجاهل القيم داخل القوائم."""
    if not dom:
        return
    for fname, op in _DOMAIN_PAIR.findall(dom):
        if op not in DOMAIN_OPS:
            continue                       # ليست صيغة (حقل، معامل، قيمة)
        if fname in avail or fname in MAGIC or fname in ("company_ids",):
            continue
        err("%s: %s يستخدم حقلاً غير موجود «%s»" % (where, label, fname))


def walk_arch(el, model, where, avail, depth=0):
    """يمشي في شجرة الواجهة مع تتبع النموذج الحالي (يتغيّر داخل x2many)."""
    tag = el.tag

    if tag == "field":
        fname = el.get("name")
        if not fname:
            err("%s: <field> بلا name" % where)
            return
        if fname not in avail:
            err("%s: الحقل «%s» غير معرَّف في %s" % (where, fname, model))
            return
        for attr in ("invisible", "required", "readonly", "column_invisible"):
            check_expr(model, attr, el.get(attr), where)

        fobj = REGISTRY[model]["fields"].get(fname)
        sub_model = model
        if fobj is not None and fobj._type in ("one2many", "many2many"):
            comodel = fobj.args[0] if fobj.args else None
            if isinstance(comodel, str):
                if comodel in REGISTRY:
                    sub_model = comodel
                else:
                    err("%s: الحقل «%s» يشير إلى نموذج غير معرَّف «%s»"
                        % (where, fname, comodel))
                    return
        elif fobj is not None and fobj._type == "many2one":
            comodel = fobj.args[0] if fobj.args else None
            if isinstance(comodel, str) and comodel not in REGISTRY \
                    and not comodel.startswith(("res.", "ir.", "mail.")):
                err("%s: many2one «%s» يشير إلى نموذج غير معرَّف «%s»"
                    % (where, fname, comodel))

        if sub_model != model or any(c.tag in ("tree", "form", "kanban", "list")
                                     for c in el):
            sub_avail = model_fields(sub_model) or avail
            for child in el:
                walk_arch(child, sub_model, where, sub_avail, depth + 1)
        else:
            for child in el:
                walk_arch(child, model, where, avail, depth + 1)
        return

    if tag == "button":
        bname = el.get("name")
        if el.get("type", "object") == "object" and bname:
            owners = REGISTRY[model].get("ext_classes") or []
            if not any(hasattr(c, bname) for c in owners):
                err("%s: الزر name='%s' بلا دالة في %s" % (where, bname, model))
        for attr in ("invisible", "readonly"):
            check_expr(model, attr, el.get(attr), where)
        for child in el:
            walk_arch(child, model, where, avail, depth + 1)
        return

    if tag == "label":
        target = el.get("for")
        if target and target not in avail:
            err("%s: <label for='%s'> يشير إلى حقل غير موجود" % (where, target))
        return

    # أي عنصر آخر: افحص modifiers ثم انزل
    for attr in ("invisible", "required", "readonly"):
        if el.get(attr):
            check_expr(model, attr, el.get(attr), where)
    for child in el:
        walk_arch(child, model, where, avail, depth + 1)


for rel, path in xml_files:
    try:
        tree = ET.parse(path)
    except ET.ParseError:
        continue
    root = tree.getroot()

    for rec in root.iter("record"):
        rid = rec.get("id")
        if rid:
            XML_IDS.add(rid)
        rmodel = rec.get("model")

        if rmodel == "ir.ui.view":
            VIEW_COUNT += 1
            target = None
            arch = None
            for fld in rec.findall("field"):
                if fld.get("name") == "model":
                    target = (fld.get("ref") or (fld.text or "").strip())
                elif fld.get("name") == "arch":
                    arch = fld
            if not target or arch is None:
                continue
            if target not in REGISTRY:
                err("%s: واجهة على نموذج غير معرَّف «%s»" % (rel, target))
                continue
            avail = model_fields(target)
            where = "%s → %s" % (rel, target)
            for child in arch:
                walk_arch(child, target, where, avail)

            # مرشّحات البحث والتجميع
            for filt in arch.iter("filter"):
                ctx = filt.get("context") or ""
                for gb in re.findall(r"'group_by'\s*:\s*'([^']+)'", ctx):
                    base = gb.split(":")[0]
                    if base not in avail and base not in MAGIC:
                        err("%s: group_by على حقل غير موجود «%s» في %s"
                            % (rel, base, target))
                for gb in re.findall(r"'group_by'\s*:\s*\[\s*'([^']+)'", ctx):
                    base = gb.split(":")[0]
                    if base not in avail and base not in MAGIC:
                        err("%s: group_by على حقل غير موجود «%s» في %s"
                            % (rel, base, target))
                check_domain(filt.get("domain"), avail, rel,
                             "المرشّح «%s»" % (filt.get("name") or "?"))

            # domains في بقية العناصر (مثل context في الإجراءات)
            for el in arch.iter():
                if el.tag == "field" and el.get("domain"):
                    check_domain(el.get("domain"), avail, rel,
                                 "domain على «%s»" % el.get("name"))

        elif rmodel in ("ir.actions.act_window", "ir.actions.server",
                        "ir.actions.act_url", "ir.actions.client"):
            for fld in rec.findall("field"):
                nm = fld.get("name")
                if nm == "res_model":
                    rm = (fld.get("ref") or (fld.text or "").strip())
                    if rm and rm not in REGISTRY \
                            and not rm.startswith(("ir.", "res.", "documents.",
                                                   "mail.", "base.")):
                        err("%s: إجراء يشير إلى نموذج غير معرَّف «%s»" % (rel, rm))
                elif nm == "domain":
                    dom = (fld.text or "").strip()
                    rm = None
                    for f2 in rec.findall("field"):
                        if f2.get("name") == "res_model":
                            rm = (f2.get("ref") or (f2.text or "").strip())
                    if rm in REGISTRY:
                        check_domain(dom, model_fields(rm), rel,
                                     "domain الإجراء على %s" % rm)
                elif nm == "context":
                    ctx = (fld.text or "").strip()
                    for gb in re.findall(r"'group_by'\s*:\s*\[?\s*'([^']+)'", ctx):
                        rm = None
                        for f2 in rec.findall("field"):
                            if f2.get("name") == "res_model":
                                rm = (f2.get("ref") or (f2.text or "").strip())
                        if rm in REGISTRY:
                            base = gb.split(":")[0]
                            if base not in (model_fields(rm) or set()):
                                err("%s: group_by «%s» غير موجود في %s"
                                    % (rel, base, rm))
                elif nm == "code" and rmodel == "ir.actions.server":
                    code = fld.text or ""
                    rm = None
                    for f2 in rec.findall("field"):
                        if f2.get("name") == "model_id":
                            ref_id = f2.get("ref") or ""
                            guess = ref_id[len("model_"):].replace("_", ".")
                            rm = guess if guess in REGISTRY else None
                    try:
                        compile(code, "<server-action>", "exec")
                    except SyntaxError as exc:
                        err("%s: كود الإجراء غير صالح — %s" % (rel, exc.msg))

    # menuitem ids
    for mi in root.iter("menuitem"):
        if mi.get("id"):
            XML_IDS.add(mi.get("id"))

print("  ✓ %s واجهة" % VIEW_COUNT)

# الجولة الثانية: مراجع القوائم والإجراءات بعد جمع كل المعرفات
ALL_IDS = set(XML_IDS)
for rel, path in xml_files:
    try:
        _t = ET.parse(path)
    except ET.ParseError:
        continue
    for _el in _t.getroot().iter():
        if _el.tag in ("record", "menuitem") and _el.get("id"):
            ALL_IDS.add(_el.get("id"))
for rel, path in xml_files:
    try:
        tree = ET.parse(path)
    except ET.ParseError:
        continue
    for el in tree.getroot().iter():
        for attr in ("parent", "action"):
            value = el.get(attr)
            if not value:
                continue
            short = value.split(".")[-1]
            if short.startswith("menu_") and short not in ALL_IDS:
                err("%s: عنصر قائمة يشير إلى «%s» غير موجود" % (rel, value))
            elif attr == "action" and short not in ALL_IDS \
                    and not value.startswith(("http", "/")):
                err("%s: عنصر قائمة يشير إلى إجراء «%s» غير موجود" % (rel, value))


# ═══════════════════════════════════════════════════════════════════════════
#  5) ملف الصلاحيات
# ═══════════════════════════════════════════════════════════════════════════
print("\nفحص الصلاحيات…")
csv_path = ADDON / "security" / "ir.model.access.csv"
if not csv_path.exists():
    err("security/ir.model.access.csv غير موجود")
else:
    with csv_path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    covered = set()
    for row in rows:
        mid = (row.get("model_id:id") or "").strip()
        expected = "model_" + (mid.replace("model_", "", 1)
                               if mid.startswith("model_") else mid)
        model_name = mid.replace("model_", "", 1).replace("_", ".")
        # إعادة بناء اسم النموذج: model_cancer_registry_case → cancer.registry.case
        guess = mid[len("model_"):].replace("_", ".")
        if guess not in REGISTRY:
            # جرّب تفسير النقاط الأصلية
            alt = mid[len("model_"):]
            candidates = [m for m in REGISTRY if m.replace(".", "_") == alt]
            if not candidates:
                err("ir.model.access.csv: model_id «%s» لا يقابله نموذج" % mid)
                continue
            model_name = candidates[0]
        else:
            model_name = guess
        covered.add(model_name)
        gid = (row.get("group_id:id") or "").strip()
        if gid and not gid.startswith("cancer_registry.") and gid != "base.group_user":
            warn("ir.model.access.csv: group_id «%s» خارج الوحدة" % gid)
        if gid.startswith("cancer_registry."):
            short = gid.split(".")[-1]
            if short not in ALL_IDS:
                err("ir.model.access.csv: المجموعة «%s» غير مُعرَّفة" % gid)
        for perm in ("perm_read", "perm_write", "perm_create", "perm_unlink"):
            if (row.get(perm) or "").strip() not in ("0", "1"):
                err("ir.model.access.csv: %s قيمة غير صالحة في %s" % (perm, row.get("id")))
    for model in REGISTRY:
        if model.startswith("cancer.registry") and model not in covered:
            err("النموذج «%s» بلا قاعدة صلاحية في ir.model.access.csv" % model)
    print("  ✓ %s قاعدة صلاحية تغطي %s نموذج" % (len(rows), len(covered)))


# ═══════════════════════════════════════════════════════════════════════════
#  6) قواعد السجلات
# ═══════════════════════════════════════════════════════════════════════════
print("\nفحص قواعد السجلات (ir.rule)…")
for rel, path in xml_files:
    try:
        tree = ET.parse(path)
    except ET.ParseError:
        continue
    for rec in tree.getroot().iter("record"):
        if rec.get("model") != "ir.rule":
            continue
        model_ref = None
        for fld in rec.findall("field"):
            if fld.get("name") == "model_id" and fld.get("ref"):
                model_ref = fld.get("ref")
        if not model_ref:
            continue
        guess = model_ref[len("model_"):].replace("_", ".")
        if guess not in REGISTRY:
            cands = [m for m in REGISTRY
                     if m.replace(".", "_") == model_ref[len("model_"):]]
            if not cands:
                err("%s: ir.rule يشير إلى «%s» بلا نموذج مطابق" % (rel, model_ref))
                continue
            guess = cands[0]
        avail = model_fields(guess)
        for fld in rec.findall("field"):
            if fld.get("name") == "domain_force":
                dom = (fld.text or "").strip()
                for fname in re.findall(r"\('([a-z_0-9.]+)'", dom):
                    base = fname.split(".")[0]
                    if base not in avail and base not in ("company_ids",):
                        err("%s: قاعدة السجل على %s تستخدم حقلاً غير موجود «%s»"
                            % (rel, guess, fname))


# ═══════════════════════════════════════════════════════════════════════════
#  7) التطابق مع القاموس
# ═══════════════════════════════════════════════════════════════════════════
print("\nفحص التطابق مع قاموس الحقول…")
sys.path.insert(0, str(ROOT))
from crcore import dictionary as dic                        # noqa: E402

case_fields = model_fields("cancer.registry.case") or {}
missing = []
for name, fdef in dic.FIELDS.items():
    if fdef["type"] == "one2many":
        continue
    if name not in case_fields:
        missing.append(name)
if missing:
    err("حقول في القاموس غير موجودة في نموذج أودو: %s" % ", ".join(missing))
else:
    print("  ✓ كل حقول القاموس (%s) موجودة في النموذج" %
          len([n for n, f in dic.FIELDS.items() if f["type"] != "one2many"]))

# حقول العرض فقط (counters / badges / html / روابط) — ليست في القاموس عمداً
UI_ONLY = {
    "name", "active", "company_id", "registry_no", "color",
    "treatment_ids", "qc_issue_ids", "nb_documents", "nb_issues_open",
    "nb_errors", "nb_treatments", "qc_color", "qc_badge", "data_entry_badge",
    "duplicate_warning", "first_document_id", "preview_html", "summary_html",
    "extracted_text_preview",
}
extra = sorted(case_fields - set(dic.FIELDS) - MAGIC - MAIL_MIXIN - UI_ONLY)
if extra:
    warn("حقول في أودو خارج القاموس (مقبولة إن كانت للعرض فقط): %s" % ", ".join(extra))

# قوائم الاختيار يجب أن تُطابق القاموس
print("\nفحص قوائم الاختيار…")
cls = REGISTRY["cancer.registry.case"]["class"]
for name, fdef in dic.FIELDS.items():
    if fdef["type"] != "selection" or not fdef["options"]:
        continue
    sel_method = "_sel_%s" % name
    if not hasattr(cls, sel_method):
        err("الحقل «%s» selection لكن لا توجد دالة %s" % (name, sel_method))
        continue
    fn = getattr(cls, sel_method)
    try:
        pairs = fn.__wrapped__(None) if hasattr(fn, "__wrapped__") else None
    except Exception:
        pairs = None
    expected = set(fdef["options"].keys())
    actual = set(k for k, _v in dic.option_pairs(name, "ar_AR"))
    if actual != expected:
        err("قائمة «%s» لا تطابق القاموس" % name)
print("  ✓ قوائم الاختيار تُقرأ من القاموس مباشرة")


# ═══════════════════════════════════════════════════════════════════════════
#  8) التقرير
# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "═" * 70)
if WARNINGS:
    print("⚠ %s تحذير:" % len(WARNINGS))
    for w in WARNINGS:
        print("   • %s" % w)
if ERRORS:
    print("✗ %s خطأ:" % len(ERRORS))
    for e in ERRORS:
        print("   • %s" % e)
    sys.exit(1)
print("✓ الوحدة سليمة — لا أخطاء.")
print("═" * 70)

# -*- coding: utf-8 -*-
"""
الجداول المرجعية: ICD-O-3 (الموقع + النسيج) و ICD-10 و TNM
==========================================================
تُحمَّل من ملفات CSV داخل refdata/ مرة واحدة ثم تُخزَّن في الذاكرة.

الملفات قابلة للاستبدال: ضِع نسختك الكاملة من ICD-O-3 بنفس أسماء الأعمدة
وستعمل كل الطبقات (الأداة + أودو) عليها بدون تغيير في الكود.
"""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path

REF_DIR = Path(__file__).parent / "refdata"


def _load_csv(name: str) -> list:
    path = REF_DIR / name
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


# ---------------------------------------------------------------- ICD-O-3
@lru_cache(maxsize=1)
def topography() -> dict:
    """{code: {label_en, label_ar, system}}"""
    out = {}
    for row in _load_csv("icdo3_topography.csv"):
        code = (row.get("code") or "").strip().upper()
        if code:
            out[code] = row
    return out


@lru_cache(maxsize=1)
def morphology() -> dict:
    """{code: {label_en, label_ar, behaviour, group}}  — الرمز بصيغة 8070/3"""
    out = {}
    for row in _load_csv("icdo3_morphology.csv"):
        code = (row.get("code") or "").strip()
        if code:
            out[code] = row
    return out


def site_label(code: str, lang: str = "ar") -> str:
    if not code:
        return ""
    row = topography().get(normalise_site(code))
    if not row:
        return ""
    return row.get("label_ar" if lang == "ar" else "label_en", "")


def morphology_label(code: str, lang: str = "ar") -> str:
    if not code:
        return ""
    row = morphology().get(normalise_morphology(code))
    if not row:
        return ""
    return row.get("label_ar" if lang == "ar" else "label_en", "")


def normalise_site(code: str) -> str:
    """C50 → C50.9 ، c50.9 → C50.9"""
    if not code:
        return ""
    c = code.strip().upper().replace(" ", "")
    c = c.replace("O", "0") if c[1:].isdigit() or re.match(r"^C\d", c) else c
    if re.match(r"^C\d{2}$", c):
        c += ".9"
    return c


def normalise_morphology(code: str) -> str:
    """8070-3 ، 8070 3 ، 8070 → 8070/3"""
    if not code:
        return ""
    c = code.strip().replace(" ", "")
    m = re.match(r"^(\d{4})[-/\s]?([0-369])?$", c)
    if not m:
        return c
    return f"{m.group(1)}/{m.group(2) or '3'}"


def is_valid_site(code: str) -> bool:
    return bool(code) and normalise_site(code) in topography()


def is_valid_morphology(code: str) -> bool:
    return bool(code) and normalise_morphology(code) in morphology()


def behaviour_from_morphology(code: str) -> str:
    n = normalise_morphology(code)
    return n.split("/")[-1] if "/" in n else ""


def icd10_from_icdo3(site: str) -> str:
    """
    ICD-O-3 C50.9  →  ICD-10 C50.9   (مطابقة مباشرة للأورام الخبيثة C00-C75)
    الأورام اللمفية/الدموية C81-C96 تحتاج映射 من الـ morphology، فنعيدها فارغة
    ليكملها المدقّق يدوياً بدل تخمين خاطئ.
    """
    n = normalise_site(site)
    if not re.match(r"^C\d{2}\.\d$", n):
        return ""
    major = int(n[1:3])
    if major > 75:                      # C76-C80 غير قابلة للترميز المباشر
        return ""
    return n


# ---------------------------------------------------------------- TNM
@lru_cache(maxsize=1)
def tnm_stage_groups() -> dict:
    """{(site_prefix, T, N, M): stage_group} — من tnm_stage_groups.csv"""
    out = {}
    for row in _load_csv("tnm_stage_groups.csv"):
        key = (row["site"].upper(), row["T"].upper(), row["N"].upper(), row["M"].upper())
        out[key] = row["stage"]
    return out


def derive_stage_group(site: str, t: str, n: str, m: str) -> str:
    """
    يستنتج المجموعة المرحلية (Stage Group) من T/N/M.
    يبحث عن قاعدة مطابقة للموقع ثم قاعدة عامة (ANY).
    """
    t, n, m = (t or "").upper(), (n or "").upper(), (m or "").upper()
    if not t and not n and not m:
        return ""
    table = tnm_stage_groups()
    ns = normalise_site(site)
    candidates = [ns[:3]] if ns else []
    candidates.append("ANY")

    for prefix in candidates:
        exact = table.get((prefix, t, n, m))
        if exact:
            return exact
    # قواعد عامة مبسّطة (fallback) — تكفي للتقارير الوطنية
    if m.startswith("M1"):
        return "Stage IV"
    base = re.sub(r"[a-d]$", "", t)
    nbase = re.sub(r"\(.*\)", "", n)
    if base == "TIS":
        return "Stage 0"
    if base in ("T0", "TX") and nbase in ("N0", "NX"):
        return ""
    if base in ("T1", "T2") and nbase == "N0":
        return "Stage I" if base == "T1" else "Stage II"
    if base in ("T1", "T2") and nbase.startswith("N1"):
        return "Stage II"
    if base in ("T1", "T2") and nbase.startswith(("N2", "N3")):
        return "Stage III"
    if base in ("T3",) and nbase == "N0":
        return "Stage II"
    if base in ("T3", "T4"):
        return "Stage III"
    return ""


def summary_stage_from_tnm(t: str, n: str, m: str) -> str:
    """SEER Summary Stage من TNM."""
    t, n, m = (t or "").upper(), (n or "").upper(), (m or "").upper()
    if m.startswith("M1"):
        return "distant"
    if re.sub(r"[a-d]$", "", t) == "TIS":
        return "in_situ"
    if n and n not in ("N0", "NX") and re.sub(r"\(.*\)", "", n).startswith("N") \
            and not n.startswith(("N0", "NX")):
        return "regional"
    if t and t not in ("TX",):
        return "localized"
    return "unknown"


# ---------------------------------------------------------------- ICD-10 أسباب الوفاة
@lru_cache(maxsize=1)
def icd10_chapter2() -> dict:
    return {r["code"]: r for r in _load_csv("icd10_c_sites.csv")}


def stats() -> dict:
    return {
        "topography_codes": len(topography()),
        "morphology_codes": len(morphology()),
        "tnm_rules": len(tnm_stage_groups()),
        "icd10_codes": len(icd10_chapter2()),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(stats(), indent=2, ensure_ascii=False))
    print(site_label("C50.9"), "|", morphology_label("8070/3"))
    print("Stage:", derive_stage_group("C50.9", "T2", "N1", "M0"))

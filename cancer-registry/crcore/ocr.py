# -*- coding: utf-8 -*-
"""
طبقة OCR — قراءة المستندات المسحوبة ضوئياً
==========================================
تُجرّب المحرّكات بالترتيب وتستخدم أول واحد متاح:

  1. Tesseract  (محلي، مجاني، يدعم العربية) ← الأفضل للمسح الضوئي
  2. نص مدمج في PDF (pypdf / pdfminer)      ← لملفات PDF المولّدة رقمياً
  3. Azure Document Intelligence            ← إن وُجد مفتاح API (اختياري)
  4. لصق يدوي للنص                          ← آخر حل، دائماً متاح

لا يحتاج هذا الملف إلى أي اعتماد ثقيل: كل الاستيرادات اختيارية.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field, asdict
from pathlib import Path

log = logging.getLogger("crcore.ocr")

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}
PDF_EXTS = {".pdf"}
TEXT_EXTS = {".txt", ".md", ".csv", ".log", ".text"}
SUPPORTED_EXTS = IMAGE_EXTS | PDF_EXTS | TEXT_EXTS


# --------------------------------------------------------------------------
@dataclass
class OCRResult:
    """نتيجة القراءة — تُمرَّر إلى طبقة الاستخراج."""
    text: str = ""
    engine: str = "none"          # tesseract | pdf-embedded | azure | manual | none
    pages: int = 0
    language: str = ""
    confidence: float = 0.0       # 0..100، متوسط ثقة الكلمات
    warnings: list = field(default_factory=list)
    filename: str = ""

    def to_dict(self):
        return asdict(self)

    @property
    def is_scanned_image(self) -> bool:
        """ملف PDF بلا نص مدمج = صورة ممسوحة ضوئياً تحتاج OCR حقيقياً."""
        return bool(self.text.strip()) and self.engine in ("tesseract", "azure", "manual")

    @property
    def needs_manual(self) -> bool:
        return self.engine == "none" or len(self.text.strip()) < 20


# --------------------------------------------------------------------------
# التوافر (Availability checks)
# --------------------------------------------------------------------------
def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def tesseract_languages() -> list:
    if not tesseract_available():
        return []
    try:
        out = subprocess.run(["tesseract", "--list-langs"], capture_output=True,
                             text=True, timeout=20)
        return [l.strip() for l in out.stdout.splitlines()[1:] if l.strip()]
    except Exception:
        return []


def pdftoppm_available() -> bool:
    """مطلوب لتحويل صفحات PDF إلى صور قبل OCR."""
    return shutil.which("pdftoppm") is not None


def engine_status() -> dict:
    """حالة المحرّكات — تُعرض في واجهة المستخدم."""
    langs = tesseract_languages()
    return {
        "tesseract": tesseract_available(),
        "tesseract_languages": langs,
        "arabic_supported": "ara" in langs,
        "pdftoppm": pdftoppm_available(),
        "pypdf": _has_module("pypdf"),
        "pdfminer": _has_module("pdfminer"),
        "azure_di": bool(os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")),
        "openai": bool(os.getenv("OPENAI_API_KEY")),
        "note": "" if tesseract_available() else
                "Tesseract غير مثبّت — سيُستخدم النص المدمج في PDF فقط. "
                "للصور الممسوحة ضوئياً ثبّته من https://github.com/UB-Mannheim/tesseract/wiki",
    }


def _has_module(name) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------
# 1) Tesseract
# --------------------------------------------------------------------------
def run_tesseract(image_path, lang: str = "ara+eng", psm: int = 6,
                  dpi: int = 300) -> OCRResult:
    """
    يشغّل tesseract على صورة واحدة.
    psm 6 = كتلة نصية موحّدة — الأفضل للتقارير الطبية.
    """
    if not tesseract_available():
        return OCRResult(warnings=["Tesseract غير مثبّت"])

    with tempfile.TemporaryDirectory() as td:
        base = os.path.join(td, "out")
        cmd = [
            "tesseract", str(image_path), base,
            "-l", lang, "--psm", str(psm), "--dpi", str(dpi),
            "tsv",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        except subprocess.TimeoutExpired:
            return OCRResult(warnings=["انتهت مهلة Tesseract (600 ثانية)"])
        except Exception as exc:                                     # pragma: no cover
            return OCRResult(warnings=[f"فشل تشغيل Tesseract: {exc}"])

        # Tesseract يكتب out.tsv فقط عند طلب tsv، لذا نشغّله مرة أخرى للنص
        txt_out = subprocess.run(
            ["tesseract", str(image_path), base, "-l", lang,
             "--psm", str(psm), "--dpi", str(dpi)],
            capture_output=True, text=True, timeout=600,
        )
        text = Path(base + ".txt").read_text(encoding="utf-8", errors="replace") \
            if Path(base + ".txt").exists() else txt_out.stdout

        conf = _parse_tsv_confidence(Path(base + ".tsv"))
        return OCRResult(
            text=text, engine="tesseract", pages=1, language=lang,
            confidence=conf, filename=str(image_path),
            warnings=[w for w in [proc.stderr.strip()] if w and "Warning" in w][:3],
        )


def _parse_tsv_confidence(tsv_path: Path) -> float:
    """متوسط ثقة الكلمات من مخرجات Tesseract TSV."""
    if not tsv_path.exists():
        return 0.0
    vals = []
    try:
        with tsv_path.open(encoding="utf-8", errors="replace") as fh:
            header = fh.readline().rstrip("\n").split("\t")
            if "conf" not in header or "text" not in header:
                return 0.0
            ci, ti = header.index("conf"), header.index("text")
            for line in fh:
                parts = line.rstrip("\n").split("\t")
                if len(parts) <= max(ci, ti) or not parts[ti].strip():
                    continue
                try:
                    c = float(parts[ci])
                except ValueError:
                    continue
                if c >= 0:
                    vals.append(c)
    except Exception:
        return 0.0
    return round(sum(vals) / len(vals), 1) if vals else 0.0


def ocr_images_with_tesseract(image_paths, lang: str = "ara+eng") -> OCRResult:
    """يقرأ عدة صور ويجمعها في نتيجة واحدة متعددة الصفحات."""
    texts, confs, warns = [], [], []
    for p in image_paths:
        r = run_tesseract(p, lang=lang)
        texts.append(r.text)
        if r.confidence:
            confs.append(r.confidence)
        warns += r.warnings
    return OCRResult(
        text="\n\n\f\n\n".join(texts),       # \f = فاصل صفحات
        engine="tesseract", pages=len(image_paths), language=lang,
        confidence=round(sum(confs) / len(confs), 1) if confs else 0.0,
        warnings=warns[:5],
    )


# --------------------------------------------------------------------------
# 2) النص المدمج في PDF (بدون OCR)
# --------------------------------------------------------------------------
def extract_pdf_text(pdf_path) -> OCRResult:
    pdf_path = Path(pdf_path)
    text, engine, warns = "", "none", []

    # pypdf أولاً (أسرع)
    try:
        import pypdf
        reader = pypdf.PdfReader(str(pdf_path))
        pages = len(reader.pages)
        chunks = [reader.pages[i].extract_text() or "" for i in range(pages)]
        text = "\n\n\f\n\n".join(chunks)
        if text.strip():
            engine = "pdf-embedded"
    except Exception as exc:
        warns.append(f"pypdf: {exc}")
        pages = 0

    # pdfminer كاحتياطي (أدق مع الجداول)
    if len(text.strip()) < 30:
        try:
            from pdfminer.high_level import extract_text as _et
            alt = _et(str(pdf_path))
            if len(alt.strip()) > len(text.strip()):
                text, engine = alt, "pdf-embedded"
            warns.append("pypdf لم يستخرج نصاً كافياً — استُخدم pdfminer")
        except Exception as exc:
            warns.append(f"pdfminer: {exc}")

    if not text.strip():
        warns.append(
            "الملف PDF لا يحتوي نصاً مدمجاً — هذه صورة ممسوحة ضوئياً وتحتاج OCR (Tesseract)."
        )

    return OCRResult(text=text, engine=engine, pages=pages, language="embedded",
                     confidence=99.0 if engine == "pdf-embedded" else 0.0,
                     warnings=warns, filename=pdf_path.name)


# --------------------------------------------------------------------------
# 3) تحويل PDF إلى صور (لتمريره إلى Tesseract)
# --------------------------------------------------------------------------
def pdf_to_images(pdf_path, out_dir=None, dpi: int = 300) -> list:
    """يحوّل صفحات PDF إلى PNG. يحتاج poppler-utils (pdftoppm)."""
    if not pdftoppm_available():
        return []
    out_dir = Path(out_dir or tempfile.mkdtemp(prefix="crc_pages_"))
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = out_dir / "page"
    subprocess.run(
        ["pdftoppm", "-r", str(dpi), "-png", str(pdf_path), str(prefix)],
        capture_output=True, timeout=900, check=False,
    )
    return sorted(str(p) for p in out_dir.glob("page-*.png"))


# --------------------------------------------------------------------------
# 4) Azure Document Intelligence (اختياري)
# --------------------------------------------------------------------------
def run_azure_di(file_path, model: str = "prebuilt-read") -> OCRResult:
    """
    يحتاج متغيّرات البيئة:
      AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT
      AZURE_DOCUMENT_INTELLIGENCE_KEY
    """
    endpoint = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
    key = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY")
    if not endpoint or not key:
        return OCRResult(warnings=["Azure Document Intelligence غير مهيّأ"])
    try:
        import requests
    except ImportError:
        return OCRResult(warnings=["مكتبة requests غير مثبّتة"])

    url = f"{endpoint.rstrip('/')}/documentintelligence/documentModels/{model}:analyze?api-version=2024-07-31"
    try:
        with open(file_path, "rb") as fh:
            data = fh.read()
        r = requests.post(url, data=data, timeout=300, headers={
            "Ocp-Apim-Subscription-Key": key, "Content-Type": "application/octet-stream",
        })
        r.raise_for_status()
        op = r.headers.get("operation-location")
        if op:
            import time
            for _ in range(60):
                time.sleep(3)
                s = requests.get(op, headers={"Ocp-Apim-Subscription-Key": key}, timeout=60)
                j = s.json()
                if j.get("status") == "succeeded":
                    break
            else:
                return OCRResult(warnings=["انتهت مهلة Azure"])
        else:
            j = r.json()
        pages = j.get("analyzeResult", {}).get("pages", [])
        text = "\n\n\f\n\n".join(p.get("content", "") for p in pages)
        confs = [w.get("confidence", 0) for p in pages for l in p.get("lines", [])
                 for w in l.get("words", [])]
        return OCRResult(text=text, engine="azure", pages=len(pages), language="auto",
                         confidence=round(sum(confs) / len(confs) * 100, 1) if confs else 0.0,
                         filename=Path(file_path).name)
    except Exception as exc:
        return OCRResult(warnings=[f"Azure DI: {exc}"])


# --------------------------------------------------------------------------
# 5) نقطة الدخول الموحّدة
# --------------------------------------------------------------------------
def read_document(file_path, prefer: str = "auto", lang: str = "ara+eng",
                  manual_text: str = "") -> OCRResult:
    """
    يقرأ ملفاً (PDF أو صورة) ويعيد النص.

    prefer:
      auto        → أفضل محرّك متاح
      tesseract   → أجبر OCR
      embedded    → نص PDF المدمج فقط
      azure       → Azure Document Intelligence
      manual      → نص مُلصق يدوياً
    """
    file_path = Path(file_path)
    if not file_path.exists():
        return OCRResult(warnings=[f"الملف غير موجود: {file_path}"], filename=file_path.name)

    if prefer == "manual" or manual_text.strip():
        return OCRResult(text=manual_text, engine="manual", pages=1, language="manual",
                         confidence=0.0, filename=file_path.name,
                         warnings=["نص مُدخل يدوياً — لا توجد ثقة آلية"])

    suffix = file_path.suffix.lower()

    if prefer == "azure" or (prefer == "auto" and os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY")):
        r = run_azure_di(file_path)
        if r.engine == "azure":
            return r

    if suffix in IMAGE_EXTS:
        if prefer in ("auto", "tesseract") and tesseract_available():
            return run_tesseract(file_path, lang=lang)
        return OCRResult(warnings=[
            "ملف صورة لكن Tesseract غير مثبّت — لا يمكن قراءته آلياً. "
            "استخدم خيار «لصق النص يدوياً».",
        ], filename=file_path.name)

    if suffix in TEXT_EXTS:
        try:
            txt = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return OCRResult(warnings=[f"تعذّرت قراءة الملف النصي: {exc}"],
                             filename=file_path.name)
        return OCRResult(text=txt, engine="text-file", pages=txt.count("\f") + 1,
                         language="raw", confidence=99.0, filename=file_path.name)

    if suffix in PDF_EXTS:
        # جرّب النص المدمج أولاً (أسرع وأدق إن وُجد)
        embedded = extract_pdf_text(file_path)
        if prefer == "embedded":
            return embedded
        if embedded.engine == "pdf-embedded" and len(embedded.text.strip()) > 120:
            return embedded

        # صورة ممسوحة ضوئياً → OCR
        if tesseract_available():
            if pdftoppm_available():
                imgs = pdf_to_images(file_path)
                if imgs:
                    r = ocr_images_with_tesseract(imgs, lang=lang)
                    r.filename = file_path.name
                    if not r.text.strip():
                        r.warnings.append("OCR لم يُخرج نصاً — قد تكون جودة المسح منخفضة")
                    return r
            r = run_tesseract(file_path, lang=lang)
            r.filename = file_path.name
            return r

        embedded.warnings.append(
            "الملف يحتاج OCR لكن Tesseract غير مثبّت. "
            "ثبّته للأفضل: Windows → UB-Mannheim installer (وتعليمات المسار في README)، "
            "أو استخدم خيار «لصق النص يدوياً»."
        )
        return embedded

    return OCRResult(warnings=[f"صيغة غير مدعومة: {suffix}"], filename=file_path.name)


# --------------------------------------------------------------------------
# 6) تنظيف النص قبل الاستخراج
# --------------------------------------------------------------------------
_AR_NUM = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_ARABIC_LETTERS_FIX = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ة": "ه", "ئ": "ي", "ؤ": "و",
})


def normalise_text(text: str) -> str:
    """
    توحيد النص: أرقام عربية→إنجليزية، إزالة تشويش OCR الشائع.
    يُطبَّق داخل الاستخراج فقط، والنص الأصلي يبقى محفوظاً كما هو.
    """
    if not text:
        return ""
    text = text.translate(_AR_NUM)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\u00a0", " ", text)
    # OCR يخلط أحياناً بين O والصفر، وبين l و 1 — نصلحها داخل الرموز الطبية
    text = re.sub(r"\b([CO])\s*([0-9]{2})\b", lambda m: m.group(1).replace("O", "C") + m.group(2), text)
    text = re.sub(r"\b(\d{4})\s*/\s*([0-369])\b", r"\1/\2", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def arabic_fold(text: str) -> str:
    """تطبيع للبحث عن كلمات عربية (يُستخدم في مطابقة العناوين فقط)."""
    return re.sub(r"\s+", " ", normalise_text(text or "").translate(_ARABIC_LETTERS_FIX)).strip()

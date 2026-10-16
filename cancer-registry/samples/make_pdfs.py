#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
توليد نماذج PDF للاختبار — reproducible sample generator
=========================================================
    python3 samples/make_pdfs.py

يُنشئ ملفات PDF بنص مدمج (text-based) لمحاكاة التقارير المولّدة رقمياً من
نظام المستشفى. النسخ الممسوحة ضوئياً (صور داخل PDF) تحتاج Tesseract + poppler.

ملاحظة: النماذج بالإنجليزية لأن توليد العربية في PDF يحتاج خطاً عربياً
(Amal / Amiri / Noto Naskh) غير متوفر في كل البيئات. مسارات الاستخراج
العربية مُختبرة عبر ملفات .txt في نفس المجلد.

المتطلبات:  pip install fpdf2
"""

from pathlib import Path

try:
    from fpdf import FPDF
except ImportError:
    raise SystemExit("ثبّت fpdf2 أولاً:  pip install fpdf2")

OUT = Path(__file__).parent


class Report(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 13)
        self.cell(0, 7, self.hospital, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 9)
        self.cell(0, 5, self.dept, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)
        self.set_draw_color(11, 46, 77)
        self.set_line_width(0.5)
        self.line(12, self.get_y(), 198, self.get_y())
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 7.5)
        self.set_text_color(120)
        self.cell(0, 8, f"Cancer Registry sample document - page {self.page_no()}/{{nb}}",
                  align="C")

    def section(self, title):
        self.set_font("Helvetica", "B", 10)
        self.set_fill_color(234, 242, 251)
        self.set_text_color(11, 46, 77)
        self.cell(0, 7, f"  {title}", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0)
        self.ln(1.5)

    def kv(self, k, v, bold_val=False):
        self.set_font("Helvetica", "", 9)
        self.cell(58, 5.5, k + ":")
        self.set_font("Helvetica", "B" if bold_val else "", 9)
        self.multi_cell(0, 5.5, str(v), new_x="LMARGIN", new_y="NEXT")

    def para(self, txt="", h=5.2):
        """فقرة نصية (لا تخلطها مع FPDF.line() الخاص بالرسم)."""
        self.set_font("Helvetica", "", 9)
        self.multi_cell(0, h, txt, new_x="LMARGIN", new_y="NEXT")

    def rule(self):
        self.ln(1)
        self.set_draw_color(200, 214, 232)
        self.set_line_width(0.2)
        self.line(12, self.get_y(), 198, self.get_y())
        self.ln(3)


def make_prostate():
    p = Report(orientation="P", format="A4")
    p.hospital = "BENGHAZI MEDICAL CENTRE - ONCOLOGY DEPARTMENT"
    p.dept = "Department of Uro-Oncology  |  Histopathology & Staging Report"
    p.add_page()
    p.set_font("Helvetica", "B", 12)
    p.cell(0, 8, "RADICAL PROSTATECTOMY - FINAL HISTOPATHOLOGY REPORT",
           align="C", new_x="LMARGIN", new_y="NEXT")
    p.ln(3)

    p.section("PATIENT IDENTIFICATION")
    p.kv("National ID", "119590334218", True)
    p.kv("Medical Record No. (MRN)", "BMC/URO/2024/03391")
    p.kv("Patient Name", "Omar Khalifa Omar Al-Zawahi")
    p.kv("Sex", "Male")
    p.kv("Date of Birth", "1959-11-08")
    p.kv("Age", "64 years")
    p.kv("District (Baladiya)", "Benghazi")
    p.kv("City", "Benghazi - Al-Berka")
    p.kv("Phone", "0915 220 774")
    p.kv("Address", "Al-Berka district, street 12, house 44, Benghazi")
    p.rule()

    p.section("NOTIFICATION")
    p.kv("Reporting facility", "Benghazi Medical Centre")
    p.kv("Notified by", "Dr. Idris Al-Shaib")
    p.kv("Date of notification", "2024-04-02")
    p.kv("Date of first symptom", "2024-01-18")
    p.kv("Date of diagnosis", "2024-02-27")
    p.kv("Basis of diagnosis", "6 - Histology of primary tumour")
    p.rule()

    p.section("TUMOUR CHARACTERISTICS  (ICD-O-3)")
    p.kv("Primary site (Topography)", "C61.9  -  Prostate gland, NOS", True)
    p.kv("Morphology", "8140/3  -  Adenocarcinoma, NOS", True)
    p.kv("Histological grade", "G2  -  Moderately differentiated")
    p.kv("Laterality", "0 - Not a paired site")
    p.kv("Gleason score", "3 + 4 = 7  (Grade Group 2)")
    p.kv("Tumour volume", "approx. 18% of gland volume")
    p.kv("Extraprostatic extension", "Present, focal, right posterolateral")
    p.kv("Seminal vesicle invasion", "Absent")
    p.kv("Surgical margins", "Positive at right posterolateral margin")
    p.kv("Lymphovascular invasion", "Absent")
    p.kv("Perineural invasion", "Present")
    p.kv("Regional lymph nodes", "0 / 12 nodes involved")
    p.para("Histology text: Prostatic acinar adenocarcinoma, Gleason score 3+4=7, "
           "with focal extraprostatic extension and perineural invasion. "
           "Margins focally involved.")
    p.rule()

    p.section("STAGING - AJCC 8th Edition")
    p.kv("Clinical TNM", "cT2c  cN0  cM0")
    p.kv("Clinical Stage", "Stage II")
    p.kv("Pathological TNM", "pT3a  pN0  pM0", True)
    p.kv("Pathological Stage", "Stage IIIA", True)
    p.kv("Summary stage (SEER)", "Regional")
    p.kv("Staging system", "AJCC 8th Edition")
    p.kv("Date of staging", "2024-03-11")
    p.kv("Metastatic sites", "None detected")
    p.kv("Biomarkers", "PSA pre-op 14.8 ng/mL; PSA post-op (day 45) 0.06 ng/mL")
    p.rule()

    p.section("TREATMENT SUMMARY")
    p.para("1) Surgery: Radical retropubic prostatectomy with bilateral pelvic "
           "lymph node dissection")
    p.kv("   Date", "2024-03-05")
    p.kv("   Facility", "Benghazi Medical Centre")
    p.kv("   Surgeon", "Dr. Idris Al-Shaib")
    p.para("2) Radiotherapy: Adjuvant EBRT to prostate bed, 66 Gy in 33 fractions")
    p.kv("   Start", "2024-05-14")
    p.kv("   End", "2024-06-28")
    p.para("3) Hormonal therapy: Bicalutamide 50 mg daily for 6 months")
    p.para("4) Chemotherapy: NOT given")
    p.para("5) Immunotherapy / targeted therapy: NOT applicable")
    p.kv("First-course treatment within 4 months", "Yes")
    p.kv("Main treatment centre", "Benghazi Medical Centre")
    p.kv("Treatment response", "Complete response (CR)")
    p.rule()

    p.section("FOLLOW-UP")
    p.kv("Vitality status", "Alive", True)
    p.kv("Last follow-up date", "2026-08-20")
    p.kv("Disease status at last contact", "No evidence of disease (NED)")
    p.kv("Recurrence", "No")
    p.kv("Source of follow-up", "Outpatient clinic visit + telephone contact")
    p.rule()

    p.section("RISK FACTORS & FAMILY HISTORY")
    p.kv("Risk factors", "Family history (brother), high-fat diet, age over 60")
    p.kv("Family history", "Brother diagnosed with prostate cancer in 2019, age 61")
    p.rule()

    p.ln(4)
    p.set_font("Helvetica", "I", 8.5)
    p.cell(0, 6, "Consultant Urologist: Dr. Idris Al-Shaib        Signature: ____________",
           new_x="LMARGIN", new_y="NEXT")
    p.cell(0, 6, "Report issued: 2024-03-11")
    p.output(str(OUT / "04_prostate_omar_119590334218.pdf"))
    print("  ✓ 04_prostate_omar_119590334218.pdf")


def make_leukaemia():
    p = Report(orientation="P", format="A4")
    p.hospital = "NATIONAL CANCER INSTITUTE - SABRATHA"
    p.dept = "Haematology & Bone Marrow Unit  |  Discharge Summary"
    p.add_page()
    p.set_font("Helvetica", "B", 12)
    p.cell(0, 8, "HAEMATO-ONCOLOGY DISCHARGE SUMMARY", align="C",
           new_x="LMARGIN", new_y="NEXT")
    p.ln(3)

    p.section("PATIENT")
    p.kv("National ID", "120110778432", True)
    p.kv("Medical Record No.", "NCI-HEM-2026-0147")
    p.kv("Patient Name", "Salma Nuri Salma Ben Amor")
    p.kv("Sex", "Female")
    p.kv("Date of Birth", "2011-06-30")
    p.kv("Age at diagnosis", "14 years")
    p.kv("District (Baladiya)", "Sabha")
    p.kv("City", "Sabha")
    p.kv("Phone", "0922 118 306")
    p.rule()

    p.section("DIAGNOSIS")
    p.kv("Date of first symptom", "2026-01-09")
    p.kv("Date of diagnosis", "2026-01-22")
    p.kv("Basis of diagnosis", "6 - Histology of primary tumour (bone marrow trephine)")
    p.kv("Primary site (ICD-O-3)", "C42.1  -  Bone marrow", True)
    p.kv("Morphology (ICD-O-3)", "9811/3  -  B-lymphoblastic leukaemia/lymphoma, NOS", True)
    p.kv("Grade", "Not applicable (G9)")
    p.kv("Laterality", "0 - Not a paired site")
    p.para("Cytogenetics: normal karyotype 46,XX. FISH negative for BCR-ABL1, "
           "negative for MLL rearrangement. Flow cytometry: CD19+, CD10+, CD34+, TdT+.")
    p.kv("Risk stratification", "Standard risk (NCI: age 1-9.99 and WBC < 50 x10^9/L)")
    p.kv("WBC at diagnosis", "18.4 x10^9/L")
    p.kv("Blasts in marrow", "82%")
    p.rule()

    p.section("STAGING")
    p.kv("Staging system", "Not applicable - leukaemia")
    p.kv("Clinical TNM", "Not applicable")
    p.kv("Summary stage", "Not applicable")
    p.kv("CNS involvement", "CNS-1 (no blasts in CSF)")
    p.kv("Metastatic sites", "None - systemic disease")
    p.rule()

    p.section("TREATMENT SUMMARY")
    p.para("1) Chemotherapy: BFM-like ALL protocol")
    p.kv("   Induction", "Vincristine, Daunorubicin, L-asparaginase, Prednisolone")
    p.kv("   CNS prophylaxis", "Intrathecal Methotrexate x 6")
    p.kv("   Consolidation cycles", "8 cycles")
    p.kv("   Start", "2026-01-28")
    p.kv("   End", "2026-09-10")
    p.kv("   Response", "Complete response (CR) - day 33 marrow MRD negative")
    p.para("2) Surgery: NOT performed (central venous line insertion only)")
    p.para("3) Radiotherapy: NOT given")
    p.para("4) Bone marrow transplant: NOT indicated at present")
    p.kv("First-course treatment within 4 months", "Yes")
    p.kv("Main treatment centre", "NCI Sabratha")
    p.rule()

    p.section("FOLLOW-UP")
    p.kv("Vitality status", "Alive", True)
    p.kv("Last follow-up date", "2026-10-05")
    p.kv("Disease status at last contact", "No evidence of disease (NED)")
    p.kv("Recurrence", "No")
    p.kv("Maintenance therapy", "6-MP + Methotrexate weekly, ongoing")
    p.rule()

    p.ln(3)
    p.set_font("Helvetica", "I", 8.5)
    p.cell(0, 6, "Consultant Haematologist: Dr. Amal Ben Sassi     Signature: ____________",
           new_x="LMARGIN", new_y="NEXT")
    p.cell(0, 6, "Report issued: 2026-10-08")
    p.output(str(OUT / "05_all_salma_120110778432.pdf"))
    print("  ✓ 05_all_salma_120110778432.pdf")


if __name__ == "__main__":
    print("توليد نماذج PDF…")
    make_prostate()
    make_leukaemia()
    print("انتهى.")

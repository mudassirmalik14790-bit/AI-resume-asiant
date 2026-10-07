"""ATS Resume Analyzer - Streamlit + Google Gemini Flash."""

import io
import json
import os
import time
from typing import List, Optional

import streamlit as st
from docx import Document
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from pypdf import PdfReader

DEFAULT_MODEL = "gemini-3.8-flash"
MAX_RESUME_CHARS = 20000
MIN_RESUME_CHARS = 100


# ---------- Output schema ----------
class SectionScore(BaseModel):
    name: str
    score: int = Field(ge=0, le=100)
    comment: str


class Improvement(BaseModel):
    priority: str  # High / Medium / Low
    issue: str
    suggestion: str


class ATSReport(BaseModel):
    ats_score: int = Field(ge=0, le=100)
    summary: str
    section_scores: List[SectionScore]
    strengths: List[str]
    improvements: List[Improvement]
    missing_keywords: List[str]


# ---------- Helpers ----------
def extract_text(uploaded_file) -> str:
    """Extract plain text from PDF, DOCX or TXT."""
    name = uploaded_file.name.lower()
    data = uploaded_file.getvalue()

    if name.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                raise ValueError("This PDF is password protected.")
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()

    if name.endswith(".docx"):
        doc = Document(io.BytesIO(data))
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text for cell in row.cells))
        return "\n".join(parts).strip()

    if name.endswith(".txt"):
        return data.decode("utf-8", errors="ignore").strip()

    raise ValueError("Unsupported file type. Upload a PDF, DOCX or TXT file.")


def build_prompt(resume_text: str, job_description: Optional[str]) -> str:
    jd_block = (
        f"\nTARGET JOB DESCRIPTION:\n{job_description.strip()}\n"
        if job_description and job_description.strip()
        else "\nNo job description was provided. Evaluate for general ATS-friendliness.\n"
    )
    return f"""You are an expert ATS (Applicant Tracking System) analyst and resume coach.
Analyze the resume below and return a structured report.

Scoring guidance (be honest and strict, do not inflate scores):
- Keyword relevance{" to the job description" if job_description and job_description.strip() else " for the candidate's field"}
- Formatting and parseability (clear headings, no tables/graphics dependence, consistent dates)
- Section completeness (contact info, summary, experience, education, skills)
- Impact (quantified achievements, strong action verbs)
- Clarity, grammar and length

Return:
- ats_score: overall score 0-100
- summary: 2-3 sentence overall assessment
- section_scores: scores 0-100 with a short comment for each of: Keywords, Formatting, Content & Impact, Completeness
- strengths: 3-6 short points
- improvements: 5-10 specific, actionable items; priority must be High, Medium or Low
- missing_keywords: important keywords/skills absent from the resume
  (only if they would genuinely fit the candidate; never suggest fabricating experience)
{jd_block}
RESUME:
\"\"\"
{resume_text[:MAX_RESUME_CHARS]}
\"\"\"
"""


def analyze_resume(api_key: str, model: str, resume_text: str, jd: Optional[str]) -> ATSReport:
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=120000),  # 120 seconds
    )
    prompt = build_prompt(resume_text, jd)
    config = types.GenerateContentConfig(
        temperature=0.2,
        response_mime_type="application/json",
        response_schema=ATSReport,
    )

    response = None
    waits = [3, 8]  # seconds to wait before retry 2 and 3
    for attempt in range(len(waits) + 1):
        try:
            response = client.models.generate_content(model=model, contents=prompt, config=config)
            break
        except Exception as e:
            msg = str(e)
            overloaded = "503" in msg or "UNAVAILABLE" in msg
            if overloaded and attempt < len(waits):
                time.sleep(waits[attempt])
                continue
            raise

    if getattr(response, "parsed", None) is not None:
        return response.parsed
    if not response.text:
        raise ValueError("The model returned an empty response. Please try again.")
    return ATSReport(**json.loads(response.text))


def get_api_key() -> str:
    try:
        key = st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        key = ""
    return key or os.environ.get("GEMINI_API_KEY", "")


def score_color(score: int) -> str:
    if score >= 80:
        return "green"
    if score >= 60:
        return "orange"
    return "red"


# ---------- UI ----------
st.set_page_config(page_title="ATS Resume Analyzer", page_icon="📄", layout="centered")
st.title("📄 ATS Resume Analyzer")
st.caption("Upload your resume to get an ATS score and concrete ways to improve it.")

with st.sidebar:
    st.header("Settings")
    api_key = get_api_key()
    if api_key:
        st.success("API key loaded from secrets.")
    else:
        api_key = st.text_input("Gemini API key", type="password",
                                help="Get a free key at https://aistudio.google.com/apikey")
    model_name = st.text_input("Model", value=DEFAULT_MODEL,
                               help="Any Gemini Flash model name, e.g. gemini-3.8-flash")
    st.markdown("---")
    st.caption("Your resume is sent to Google's Gemini API for analysis and is not stored by this app.")

uploaded = st.file_uploader("Upload resume", type=["pdf", "docx", "txt"])
job_description = st.text_area(
    "Job description (optional)",
    height=150,
    placeholder="Paste the job posting here for a tailored keyword match...",
)

if st.button("Analyze resume", type="primary", disabled=uploaded is None):
    if not api_key:
        st.error("Please enter your Gemini API key in the sidebar.")
        st.stop()

    try:
        with st.spinner("Reading resume..."):
            text = extract_text(uploaded)
    except Exception as e:
        st.error(f"Could not read the file: {e}")
        st.stop()

    if len(text) < MIN_RESUME_CHARS:
        st.error(
            "Very little text could be extracted. If your resume is a scanned image, "
            "export it as a text-based PDF or upload a DOCX instead."
        )
        st.stop()

    try:
        with st.spinner("Analyzing with Gemini..."):
            report = analyze_resume(api_key, model_name.strip() or DEFAULT_MODEL, text, job_description)
    except Exception as e:
        msg = str(e)
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
            st.warning("Too many requests (free tier limit). Please wait about a minute and try again.")
        elif "503" in msg or "UNAVAILABLE" in msg:
            st.warning("Google's model is busy right now. Please try again in a minute or two.")
        elif "404" in msg or "NOT_FOUND" in msg:
            st.error("Model not found. Change the model name in the sidebar to a current Gemini Flash model.")
        elif "timed out" in msg.lower() or "timeout" in msg.lower() or "deadline" in msg.lower():
            st.error("The request timed out. Please try again.")
        else:
            st.error(f"Analysis failed: {e}")
        st.stop()

    st.divider()
    st.subheader("Your ATS score")
    st.markdown(f"## :{score_color(report.ats_score)}[{report.ats_score} / 100]")
    st.progress(report.ats_score / 100)
    st.write(report.summary)

    st.subheader("Section breakdown")
    for sec in report.section_scores:
        st.write(f"**{sec.name}**: {sec.score}/100")
        st.progress(sec.score / 100)
        st.caption(sec.comment)

    st.subheader("✅ Strengths")
    for s in report.strengths:
        st.markdown(f"- {s}")

    st.subheader("🛠️ Improvements")
    order = {"high": 0, "medium": 1, "low": 2}
    icons = {"high": "🔴", "medium": "🟠", "low": "🟢"}
    for imp in sorted(report.improvements, key=lambda i: order.get(i.priority.lower(), 3)):
        icon = icons.get(imp.priority.lower(), "⚪")
        with st.expander(f"{icon} {imp.priority}: {imp.issue}"):
            st.write(imp.suggestion)

    if report.missing_keywords:
        st.subheader("🔑 Missing keywords")
        st.write(", ".join(f"`{k}`" for k in report.missing_keywords))

    st.caption("This score is an AI estimate. Real ATS systems vary, so use it as guidance.")

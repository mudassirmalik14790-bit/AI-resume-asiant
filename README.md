# 📄 ATS Resume Analyzer

A Streamlit app that scores your resume for Applicant Tracking Systems (ATS) and gives specific improvements, powered by Google Gemini Flash.

## Features
- Upload a resume as **PDF, DOCX or TXT**
- Optional **job description** for tailored keyword matching
- Overall **ATS score (0-100)** plus a section breakdown
- Strengths, **prioritized improvements**, and missing keywords

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```
Enter your Gemini API key in the sidebar, or set it once:

```bash
# Mac/Linux
export GEMINI_API_KEY="your_key"
# Windows PowerShell
$env:GEMINI_API_KEY="your_key"
```

Get a free key at https://aistudio.google.com/apikey

## Deploy on Streamlit Community Cloud
1. Push this repo to GitHub (never commit your API key).
2. Go to https://share.streamlit.io and click **Create app**.
3. Select your repo, branch `main`, main file `app.py`.
4. Open **Advanced settings → Secrets** and paste:
   ```toml
   GEMINI_API_KEY = "your_key_here"
   ```
5. Click **Deploy**.

## Notes
- The default model is `gemini-2.5-flash`. You can change it in the sidebar if Google releases a newer Flash model.
- Scanned (image-only) PDFs can't be read. Use a text-based PDF or DOCX.
- The score is an AI estimate, not an official ATS result.

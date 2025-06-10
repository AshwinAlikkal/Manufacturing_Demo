# modules/utils.py   – full file with stronger logging + safer PDF upload
import os
import sys
import base64
from math import ceil
from datetime import datetime,timedelta

import numpy as np
import pandas as pd
import markdown
from scipy.optimize import linprog
from dotenv import load_dotenv
from openai import OpenAI
from huggingface_hub import InferenceClient, login
from xhtml2pdf import pisa

from modules import prompts, gcs
import config
from modules.logger import get_log_stream, upload_log_to_gcs, get_logger

from PIL import Image
import google.generativeai as genai
import re
from io import BytesIO
import pdfplumber
import json
# ─────────────────────────────────────────────
# Logger
# ─────────────────────────────────────────────
load_dotenv()
logger = get_logger()

def _log_long(txt: str, label: str, head: int = 800) -> None:
    """
    Helper: log long strings without spamming the log file.
    Keeps the first `head` characters (default 800).
    """
    snippet = txt 
    logger.info("%s (%d chars)\n%s", label, len(txt), snippet)

# ─────────────────────────────────────────────
# API keys
# ─────────────────────────────────────────────
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY")
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# ─────────────────────────────────────────────
# Utility functions
# ─────────────────────────────────────────────
def encode_image(path: str) -> str:
    """Load an image (local or GCS) and return a base-64 data-URL string."""
    try:
        image_bytes = gcs.read_bytes(path, config.local_eda_flag)
        logger.info("Encoded image at %s", path)
        return (
            "data:image/png;base64,"
            + base64.b64encode(image_bytes).decode("utf-8")
        )
    except Exception as e:
        logger.error("Failed to encode image at %s: %s", path, e)
        raise

# ─────────────────────────────────────────────
# 1. Manufacturing analysis (plots → LLM)
# ─────────────────────────────────────────────
def generate_manufacturing_analysis() -> str:
    """
    Loop over the three combined EDA plots (one per line), send each to an LLM
    and build a single markdown section containing all analyses.
    """
    try:
        image_paths = [
            config.line1_combined_analysis_path,
            config.line2_combined_analysis_path,
            config.line3_combined_analysis_path,
        ]
        titles = [
            "Plot 1 : Line 1 Combined EDA",
            "Plot 2 : Line 2 Combined EDA",
            "Plot 3 : Line 3 Combined EDA",
        ]
        manufacturing_system_prompt = prompts.manufacturing_system_prompt
        combined_md = ""

        if config.USE_OPENAI:
            client = OpenAI(api_key=OPENAI_API_KEY)
            logger.info("Using OpenAI for manufacturing analysis.")
        else:
            login(HUGGINGFACE_API_KEY)
            client = InferenceClient(config.huggingface_model,
                                     token=HUGGINGFACE_API_KEY)
            logger.info("Using HuggingFace for manufacturing analysis.")

        for title, path in zip(titles, image_paths):
            try:
                encoded = encode_image(path)
                messages = [
                    {"role": "system", "content": manufacturing_system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": title},
                            {"type": "image_url",
                             "image_url": {"url": encoded}},
                        ],
                    },
                ]
                if config.USE_OPENAI:
                    resp = client.chat.completions.create(
                        model=config.gpt_model, messages=messages
                    )
                    analysis = resp.choices[0].message.content
                else:
                    resp = client.chat.completions.create(
                        model=config.huggingface_model, messages=messages
                    )
                    analysis = resp.choices[0].message.content

                _log_long(analysis, f"{title}-analysis")
                combined_md += f"\n\n### {title}\n{analysis}"
                logger.info("Analysis generated for %s", title)

            except Exception as e:
                logger.error("%s analysis failed: %s", title, e)
                combined_md += f"\n\n### {title}\nAnalysis failed: {e}"

        logger.info("Manufacturing analysis complete.")
        return combined_md

    except Exception as e:
        logger.error("generate_manufacturing_analysis failed: %s", e)
        raise

# ─────────────────────────────────────────────
# 2. Recovery plan (LP optimisation → text)
# ─────────────────────────────────────────────
def run_recovery_text_output(start_date, start_shift) -> str:
    """
    Optimise a deficit-recovery schedule.
    Returns a plain-text block.
    """
    try:
        # 1️⃣ Load & preprocess
        df = gcs.load_dataframe(config.cleaned_path, config.local_data_flag)
        df["Date"] = pd.to_datetime(df["Date"])
        df["shift_time"] = np.where(
            df["Shift"] == "Day",
            df["Date"] + pd.Timedelta(hours=12),
            df["Date"] + pd.Timedelta(hours=20),
        )
        df = df.sort_values("shift_time").reset_index(drop=True)

        # 2️⃣ Cut-off timestamp
        cut = pd.to_datetime(start_date) + (
            pd.Timedelta(hours=12) if start_shift == "Day"
            else pd.Timedelta(hours=20)
        )

        # 3️⃣ Split baseline / window
        baseline = df[df["shift_time"] < cut]
        window   = df[df["shift_time"] >= cut]

        D = window["Production_Deficit"].sum()
        # overall avg hours per LINE (both shifts combined—as before)
        avg_line  = baseline.groupby("Production Line")["Machine Operation Time (hrs)"].mean()
        rate_line = window.groupby("Production Line")["Production Rate (units/hr)"].mean()

        # NEW: per-shift averages for the baseline period
        avg_by_shift = (
            baseline
            .groupby(["Production Line","Shift"])["Machine Operation Time (hrs)"]
            .mean()
            .unstack()   # yields columns ['Day','Night']
        )

        lines = sorted(set(avg_line.index).intersection(rate_line.index))
        avg   = avg_line.loc[lines].values
        rate  = rate_line.loc[lines].values

        # LP setup (unchanged)
        bounds = [(max(0, 6 - ai), max(0, 10 - ai)) for ai in avg]
        c   = -rate
        A_ub = rate.reshape(1, -1)
        b_ub = [D]

        # 4️⃣ Single-day LP
        sol = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")
        if sol.success and (rate @ sol.x) >= D - 1e-6:
            s_opt = sol.x
            h_opt = avg + s_opt
            produced = float((rate * s_opt).sum())

            # extract per-shift avg arrays
            avg_day   = avg_by_shift.loc[lines, "Day"].values
            avg_night = avg_by_shift.loc[lines, "Night"].values

            sched = pd.DataFrame({
                "Production Line":    lines,
                "Avg Hours (all)  ":  avg,
                "Opt Hours (all)  ":  h_opt,
                "% Increase Day    ": 100 * s_opt / avg_day,
                "% Increase Night  ": 100 * s_opt / avg_night,
                "Extra Prod (units)":  rate * s_opt,
            }).round(2)

            sched_date = (pd.to_datetime(start_date) + pd.Timedelta(days=1)).date()

            out = [
                f"Total Deficit from {start_date} {start_shift} shift: {D:.1f} units",
                f"\nSingle-Day Schedule for {sched_date}:",
                sched.to_string(index=False),
                f"\nTotal Produced Against Deficit: {produced:.1f} units",
            ]
            result = "\n\n".join(out)
            _log_long(result, "single-day-recovery-plan")
            return result

        # 5️⃣ Multi-day fallback (unchanged), but add the two % columns similarly
        max_daily = ((10 - avg) * rate).sum()
        days = ceil(D / max_daily)
        daily_def = D / days

        denom = np.dot(rate, rate)
        s_prop  = daily_def * rate / denom
        h_daily = np.clip(avg + s_prop, 6, 10)

        avg_day   = avg_by_shift.loc[lines, "Day"].values
        avg_night = avg_by_shift.loc[lines, "Night"].values

        sched = pd.DataFrame({
            "Production Line":   lines,
            "Avg Hours (all)    ": avg,
            "Daily Hours required": h_daily,
            "% Increase Day      ": 100 * (h_daily - avg) / avg_day,
            "% Increase Night    ": 100 * (h_daily - avg) / avg_night,
        }).round(2)

        out = [
            f"Total Deficit from {start_date} {start_shift} shift: {D:.1f} units",
            f"\nRequires minimum {days} days to recover deficit.",
            "\nDaily Schedule (shift-wise):",
            sched.to_string(index=False),
        ]
        result = "\n\n".join(out)
        _log_long(result, "multi-day-recovery-plan")
        return result

    except Exception as e:
        logger.error("run_recovery_text_output failed: %s", e)
        return f"Failed to compute recovery plan: {e}"

# ─────────────────────────────────────────────
# 3. Build full markdown report (LLM)
# ─────────────────────────────────────────────
def build_report_string(prompt: str) -> str:
    """Call OpenAI with the full prompt and return the markdown report string."""
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=config.gpt_model,
            messages=[{"role": "system", "content": prompt}],
            temperature=0.0,
        )
        md = response.choices[0].message.content
        _log_long(md, "build_report_string-return")
        return md
    except Exception as e:
        logger.error("build_report_string failed: %s", e)
        return f"Failed to generate report string: {e}"

# ─────────────────────────────────────────────
# 4. Convert markdown → PDF (local or GCS)
# ─────────────────────────────────────────────
def pdf_creation(md_content: str, save_path: str) -> str:
    """
    Convert markdown to HTML, render it to a PDF and store it either locally
    or in the configured GCS bucket.
    """
    try:
        if not save_path:
            raise ValueError("PDF creation requires an explicit save_path.")

        html_body = markdown.markdown(md_content, extensions=["extra"])
        html_full = prompts.build_html_content(html_body)

        # ----- Render HTML → PDF (in-memory) -----
        from io import BytesIO
        output = BytesIO()
        pisa_status = pisa.CreatePDF(html_full, dest=output)
        if pisa_status.err:
            raise RuntimeError(f"xhtml2pdf returned {pisa_status.err} error(s).")
        output.seek(0)

        if config.local_report_flag:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(output.read())
            logger.info("PDF saved locally → %s", save_path)

        else:
            # Upload to GCS
            gcs.upload_blob_from_bytes(
                content=output.read(),
                destination_blob_name=save_path,
                content_type="application/pdf",
            )

            # quick sanity check
            bucket = gcs._get_bucket()
            if not bucket.blob(save_path).exists():
                raise RuntimeError(f"GCS upload succeeded but blob {save_path} "
                                   "is not found afterwards.")
            logger.info("PDF uploaded to GCS → %s", save_path)

        return save_path

    except Exception as e:
        logger.error("pdf_creation failed (%s): %s", save_path, e)
        return f"PDF creation failed: {e}"
    
def parse_rows(rows, columns):
    parsed = []
    for idx, row in enumerate(rows, 1):
        parts = [cell.strip() for cell in row.split("|", maxsplit=len(columns)-1)]
        if len(parts) != len(columns):
            logger.warning(f"Skipping malformed row {idx}: expected {len(columns)} fields, got {len(parts)}")
            continue
        parsed.append(parts)
    return pd.DataFrame(parsed, columns=columns)

## Function for OCR_IMPLEMENTATION

def OCR_implementation(uploaded_files):
    """
    Run OCR on a list of uploaded image files, extract tabular text,
    normalize delimiters, and return clean DataFrames for production and issues.
    """

    # Configure Gemini OCR
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel(config.ocr_model)

    # Define expected headers and columns
    HEADER_Production = (
        "Date | Production Line | Shift | "
        "Machine operating time (hrs) | Production Rate(units/hr)"
    )
    HEADER_Issues = (
        "Date | Production Line | Shift | "
        "Issue Severity Major | Issue Severity Minor | "
        "Issue Severity No issues | Comments"
    )
    columns_production = [col.strip() for col in HEADER_Production.split("|")]
    columns_issues = [col.strip() for col in HEADER_Issues.split("|")]

    production_rows = []
    issues_rows = []

    for uploaded_file in uploaded_files:
        try:
            filename = uploaded_file.name.lower()
            image = Image.open(uploaded_file)
            logger.info(f"Processing file: {uploaded_file.name}")

            # Determine prompt and expected columns
            if "production" in filename:
                prompt = prompts.ocr_prompt_production
                expected_columns = columns_production
            elif "issues" in filename:
                prompt = prompts.ocr_prompt_issues
                expected_columns = columns_issues
            else:
                logger.warning(f"Skipping file without valid prefix: {uploaded_file.name}")
                continue

            # Run OCR
            resp = model.generate_content([prompt, image])
            extracted_text = resp.text.strip()
            logger.info(f"OCR Extracted Text:\n{extracted_text}")

            # Parse output lines that look like rows
            lines = [
                line.strip()
                for line in extracted_text.splitlines()
                if "|" in line and not re.match(r'^\|?-+\|?$', line)
            ]

            # Remove potential header rows
            filtered_lines = [
                line for line in lines
                if not ("Date" in line and "Production Line" in line)
            ]

            # Extract data rows
            parsed_rows = []
            for line in filtered_lines:
                parts = [cell.strip() for cell in line.split("|")]
                parts = parts[:len(expected_columns)]  # Trim to expected size
                if len(parts) == len(expected_columns):
                    parsed_rows.append(parts)
                else:
                    logger.warning(f"Skipping malformed row: {line}")

            if "production" in filename:
                production_rows.extend(parsed_rows)
            elif "issues" in filename:
                issues_rows.extend(parsed_rows)

            logger.info(f"OCR completed for file: {uploaded_file.name}")

        except Exception as e:
            logger.error(f"OCR failed for {uploaded_file.name}: {e}")

    # Construct final DataFrames
    df_production = pd.DataFrame(production_rows, columns=columns_production) if production_rows else pd.DataFrame(columns=columns_production)
    df_issues = pd.DataFrame(issues_rows, columns=columns_issues) if issues_rows else pd.DataFrame(columns=columns_issues)

    logger.info(f"Production shape: {df_production.shape}, Issues shape: {df_issues.shape}")
    return df_production, df_issues

## ---> Extracting text from pdf using pdfplumber

def full_text_from_report(report_path, is_local=True):
    if is_local:
        with pdfplumber.open(report_path) as pdf:
            full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    else:
        pdf_bytes = gcs.read_bytes(report_path, is_local=False)
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    return full_text


## ---> Final Production plan generation in a dataframe format
def recovery_summary_and_plan_from_text(full_text, cleaned_csv_path, prod_rate_map=None,):
    """
    1. Calls Gemini to extract recovery JSON from full_text.
    2. Generates summary DataFrame and production plan DataFrame.
    Returns: summary_df, plan_df
    """
    if prod_rate_map is None:
        prod_rate_map = {"Line1": 140, "Line2": 150, "Line3": 130}

    # --- Gemini call for JSON extraction ---
    prompt = prompts.production_recovery_prompt(full_text)
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=config.gpt_model,
        messages=[{"role": "system", "content": prompt}],
        temperature=0.0,
    )
    content = response.choices[0].message.content.strip()
    match = re.search(r'(\[\s*{.*?}\s*\])', content, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        json_str = content
    try:
        summary_list = json.loads(json_str)
        for rec in summary_list:
            try:
                rec["Recovery Days"] = int(rec["Recovery Days"])
            except (ValueError, KeyError):
                rec["Recovery Days"] = 0
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON:\n{json_str}") from e

    # --- DataFrame generation ---
    line_summary = pd.DataFrame(summary_list)
    cleaned_df = gcs.load_dataframe(cleaned_csv_path, is_local=config.local_data_flag)
    cleaned_df['Date'] = pd.to_datetime(cleaned_df['Date'])  # Ensures correct type
    last_date  = cleaned_df['Date'].max()
    last_shift = cleaned_df[cleaned_df['Date'] == last_date]['Shift'].iloc[-1]


    def next_shift(date, shift):
        if shift == 'Day':
            return date, 'Night'
        return date + timedelta(days=1), 'Day'

    plan_rows = []
    for rec in summary_list:
        line = rec["Production Line"]
        rec_hours = rec["Recommended Hours (hrs/day)"]
        inc_day   = rec["Increase (%) Day"]
        inc_night = rec["Increase (%) Night"]
        days      = rec["Recovery Days"]

        d, s = next_shift(last_date, last_shift)
        for _ in range(days * 2):  # two shifts per day
            plan_rows.append({
                "Date":                            d.strftime("%Y-%m-%d"),
                "Production Line":                 line,
                "Shift":                           s,
                "Machine operating hours recommended": rec_hours,
                "Production Rate (units/hr)":      prod_rate_map[line.replace(' ', '')],
                "Increase (%)":                    inc_day if s == "Day" else inc_night
            })
            d, s = next_shift(d, s)

    production_plan = pd.DataFrame(plan_rows)
    return line_summary, production_plan

# ─────────────────────────────────────────────
# 5. Push logs to GCS at module exit (cloud mode)
# ─────────────────────────────────────────────
if not config.local_log_flag:
    try:
        stream = get_log_stream()
        if stream is not None:
            upload_log_to_gcs(stream.getvalue(), gcs)
            stream.truncate(0)
            stream.seek(0)
            logger.info("Logs uploaded to GCS and stream cleared (utils.py).")
    except Exception as e:
        logger.error("Log upload at utils.py exit failed: %s", e)

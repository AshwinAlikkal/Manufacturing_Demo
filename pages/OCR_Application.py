import pandas as pd
import streamlit as st
import re
from PIL import Image
from io import StringIO
import google.generativeai as genai
import config
from dotenv import load_dotenv
from modules import gcs
from modules.logger import init_logger, get_logger, upload_log_to_gcs, get_log_stream
from modules import prompts
import os
import logging

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ─────────────────────────────────────────────
# Logger setup
# ─────────────────────────────────────────────
init_logger(config.local_log_flag)
logger = logging.getLogger("manufacturing_logger")

# ─────────────────────────────────────────────
# Load Gemini model
# ─────────────────────────────────────────────

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(config.ocr_model)

# ─────────────────────────────────────────────
# Streamlit page config
# ─────────────────────────────────────────────
st.set_page_config(page_title="OCR with Gemini", layout="wide")
st.title("📝 OCR Handwriting Recognition with Gemini")

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────
HEADER = "Date | Production Line | Shift | Machine operating time (hrs) | Production Rate(units/hr) | Issue Severity Major | Issue Severity Minor | Issue Severity No issues | Comments"

# ─────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────

def process_uploaded_images(uploaded_files):
    all_rows = []

    for i, uploaded_file in enumerate(uploaded_files, start=1):
        try:
            image = Image.open(uploaded_file)
            logger.info(f"Processing file: {uploaded_file.name}")

            response = model.generate_content([
                """Extract all handwritten text from this image written in the form of a table. 
                Use the following columns only: Date, Production Line, Shift, Machine operating time (hrs), 
                Production Rate(units/hr), Issue Severity Major, Issue Severity Minor, Issue Severity No issues, Comments.
                - Date: The date in the format is MM/DD/YYYY
                - Production Line: The name of the production line (Either it is Line 1 or Line 2 or Line 3)
                - Shift: The shift during which the record was made (Either it is Day or Night)
                - Machine operating time (hrs): The total operating time of the machine in hours
                - Production Rate (units/hr): The production rate in units per hour
                - Issue Severity Major: Indicates if there are any major issues (Yes or No)
                - Issue Severity Minor: Indicates if there are any minor issues (Yes or No)
                - Issue Severity No Issues: Indicates if there are no issues (Yes or No)
                - Comments: Any additional comments or notes  
                If the header is missing, assume the above column headers. Output the table using '|' delimiters with one row per line.
                """,
                image
            ])
            extracted_text = response.text.strip()
            logger.info(extracted_text)
            lines = [line.strip() for line in extracted_text.split('\n')
                     if '|' in line and not re.match(r'^\|?-+\|?$', line)]
            for line in lines:
                if "Date" in line and "Production Line" in line:
                    continue
                all_rows.append(line)

            logger.info(f"OCR completed for file: {uploaded_file.name}")

        except Exception as e:
            logger.error(f"OCR failed for {uploaded_file.name}: {e}")

    # Final table with header
    final_table = [HEADER] + all_rows
    final_text = "\n".join(final_table)

    try:
        df = pd.read_csv(StringIO(final_text), sep="|")
        df.columns = [col.strip() for col in df.columns]

        # Strip whitespace from all cells
        df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)

        logger.info(f"Final DataFrame shape after trimming: {df.shape}")
        return df

    except Exception as e:
        logger.error(f"Failed to parse extracted data into DataFrame: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────
# Main UI – Upload and Process
# ─────────────────────────────────────────────
try:
    with st.expander("📂 Upload handwritten images", expanded=True):
        with st.form("ocr_form"):
            uploads = st.file_uploader(
                "Upload one or more handwritten image files",
                type=["jpg", "jpeg", "png"],
                accept_multiple_files=True
            )
            submitted = st.form_submit_button("🚀 Run OCR")

        if submitted:
            if not uploads:
                st.error("Please upload at least one file.")
                logger.warning("No files uploaded.")
                st.stop()

            with st.spinner("Running OCR and extracting data..."):
                df = process_uploaded_images(uploads)

            if not df.empty:
                st.subheader("📊 Cleaned Data Preview")
                st.write(df)
                st.download_button(
                    label="📥 Download CSV",
                    data=df.to_csv(index=False).encode("utf-8"),
                    file_name="ocr_results.csv",
                    mime="text/csv"
                )
                # For Constructing the structure of the folder
                ocr_path = config.ocr_data_saved_path

                # For finally saving the folder
                gcs.save_dataframe(df, ocr_path, is_local=config.local_ocr_flag)
            else:
                st.error("⚠️ No valid data extracted from the uploaded images.")
                logger.warning("OCR processing completed with empty DataFrame.")

except Exception as e:
    logger.error(f"Unexpected error in OCR application: {e}")
    st.error("Unexpected error. Please check the logs.")


# ─────────────────────────────────────────────
# Upload logs to GCS (cloud mode)
# ─────────────────────────────────────────────
if not config.local_log_flag:
    try:
        log_stream = get_log_stream()
        if log_stream is not None:
            log_content = log_stream.getvalue()
            upload_log_to_gcs(log_content, gcs_module=gcs)
            log_stream.truncate(0)
            log_stream.seek(0)
            logger.info("Logs uploaded to GCS and log stream cleared.")
    except Exception as e:
        logger.error(f"Failed to upload logs to GCS at end of OCR app: {e}")

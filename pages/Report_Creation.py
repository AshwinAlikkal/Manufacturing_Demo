# pages/2_Report_Creation.py – GCS/local compliant version
# (Fix #1 **plus**: log the actual LLM / prompt outputs)

import os
from datetime import date
import streamlit as st
from streamlit_pdf_viewer import pdf_viewer
import pandas as pd
import logging

from modules import utils, EDA_backend, prompts, gcs
import config
from modules.logger import (
    init_logger,
    get_log_stream,
    upload_log_to_gcs,
    get_logger,
)

# ─────────────────────────────────────────────
# Logger Setup
# ─────────────────────────────────────────────
init_logger(config.local_log_flag)
logger = get_logger()
logger.info("Report Creation page loaded.")

# Helper to avoid megabyte-sized log files
def _log_long(txt, label: str, head: int = 800):
    snippet = txt
    logger.info("%s (%d chars)\n%s", label, len(txt), snippet)

# ─────────────────────────────────────────────
# Streamlit page
# ─────────────────────────────────────────────
st.set_page_config(page_title="Report Creation", page_icon="📝", layout="wide")
st.title("📝 Manufacturing Analytics – Report Creator")

# ─────────────────────────────────────────────
# 1️⃣ Parameter picker
# ─────────────────────────────────────────────
try:
    with st.expander("⚙️ Report Parameters", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            report_date = st.date_input("Select Report Date", date.today())
        with c2:
            shift = st.selectbox("Select Shift", ["Day", "Night"])

        st.session_state.setdefault("report_generated", False)
        st.session_state.setdefault("report_path", None)

        if st.button("🚀 Generate / View Report"):
            try:
                with st.spinner("Working…"):
                    safe_date = report_date.strftime("%Y-%m-%d")
                    out_path = f"Reports_Created/Report_{safe_date}_{shift}.pdf"
                    logger.info("Report generation triggered for %s %s -> %s",
                                safe_date, shift, out_path)

                    # ✅ Use existing local report if allowed
                    if config.local_report_flag and os.path.exists(out_path):
                        st.session_state.update(report_path=out_path,
                                                report_generated=True)
                        st.toast("✔️ Re-using existing PDF", icon="📄")
                        logger.info("Re-used existing local report at %s", out_path)

                    else:
                        # 1️⃣ Load cleaned data
                        try:
                            df = gcs.load_dataframe(
                                config.cleaned_path, config.local_data_flag)
                            lines = df["Production Line"].dropna().unique()
                            logger.info("Loaded cleaned data for report.")
                        except Exception as e:
                            logger.error("Failed to load cleaned data: %s", e)
                            st.error("Error loading cleaned data.")
                            st.stop()

                        # 2️⃣ Save backend plots
                        paths = {
                            "Line1": config.line1_combined_analysis_path,
                            "Line2": config.line2_combined_analysis_path,
                            "Line3": config.line3_combined_analysis_path,
                        }
                        for line in lines:
                            if line in paths:
                                try:
                                    EDA_backend.create_combined_linewise_figure(
                                        df=df,
                                        line=line,
                                        save_path=paths[line],
                                        date=safe_date,
                                        shift=shift,
                                    )
                                    logger.info("Backend plot saved -> %s", paths[line])
                                except Exception as e:
                                    logger.error("Plot gen failed for %s: %s", line, e)
                                    st.error(f"Error generating plot for {line}")

                        # 3️⃣ Generate report components
                        try:
                            prod_issue = utils.generate_manufacturing_analysis()
                            _log_long(prod_issue, "prod_issue")
                        except Exception as e:
                            logger.error("Manufacturing analysis gen failed: %s", e)
                            st.error("Failed to generate manufacturing analysis.")
                            st.stop()

                        try:
                            deficit = utils.run_recovery_text_output(report_date, shift)
                            _log_long(deficit, "deficit")
                        except Exception as e:
                            logger.error("Deficit plan gen failed: %s", e)
                            deficit = "Deficit plan generation failed."

                        try:
                            metrics_df = gcs.load_dataframe(
                                config.linewise_pivot_data_filepath,
                                config.local_data_flag,
                            )
                            metrics = metrics_df.to_string()
                            _log_long(metrics, "metrics")
                        except Exception as e:
                            logger.error("Failed to load metrics: %s", e)
                            metrics = "Failed to load metrics."

                        try:
                            user_prompt = prompts.prompt_generation(
                                prod_issue, deficit, metrics, report_date, shift)
                            _log_long(user_prompt, "full_prompt_to_LLM")
                            md_report = utils.build_report_string(user_prompt)
                            _log_long(md_report, "md_report (pre-PDF)")
                            
                        except Exception as e:
                            logger.error("Markdown generation failed: %s", e)
                            st.error("Failed to generate report markdown.")
                            st.stop()

                        try:
                            saved_pdf = utils.pdf_creation(md_report, save_path=out_path)
                            logger.info("PDF report written -> %s", saved_pdf)
                            st.session_state.update(report_path=out_path,
                                                    report_generated=True)
                            st.toast("✅ PDF generated", icon="✅")
                        except Exception as e:
                            logger.error("PDF creation failed: %s", e)
                            st.error("PDF creation failed.")
                            st.stop()

                st.success("Report ready!")
                logger.info("Report generation completed (%s %s).", safe_date, shift)

            except Exception as e:
                logger.error("Report generation failed: %s", e)
                st.error(f"Report generation failed: {e}")

except Exception as e:
    logger.error("Parameter section failed: %s", e)
    st.error("Failed to set report parameters.")

# ─────────────────────────────────────────────
# 2️⃣ Show PDF viewer + Download
# ─────────────────────────────────────────────
try:
    if st.session_state.get("report_generated") and st.session_state.get("report_path"):
        st.header("📄 Report Preview")
        pdf_path = st.session_state.report_path

        if config.local_report_flag:    # Local mode
            try:
                pdf_viewer(pdf_path, width=900, height=720)
                with open(pdf_path, "rb") as f:
                    pdf_bytes = f.read()
                logger.info("PDF viewed locally (%s)", pdf_path)
            except Exception as e:
                logger.error("Error viewing local PDF: %s", e)
                st.error(f"Error viewing PDF: {e}")
                pdf_bytes = b""
        else:                           # GCS mode
            try:
                pdf_bytes = gcs.read_bytes(pdf_path, is_local=False)
                tmp_path = f"/tmp/{os.path.basename(pdf_path)}"
                with open(tmp_path, "wb") as f:
                    f.write(pdf_bytes)
                pdf_viewer(tmp_path, width=900, height=720)
                logger.info("PDF fetched from GCS (%s)", pdf_path)
            except Exception as e:
                logger.error("Error fetching PDF from GCS: %s", e)
                st.error(f"Error fetching PDF from GCS: {e}")
                pdf_bytes = b""

        st.download_button("Download PDF",
                           pdf_bytes,
                           file_name=os.path.basename(pdf_path),
                           mime="application/pdf")
        logger.info("Download button rendered.")
    else:
        st.info("Select parameters and click **Generate / View Report**.")
except Exception as e:
    logger.error("PDF preview/download failed: %s", e)
    st.error("Error displaying PDF preview or download.")

# ─────────────────────────────────────────────
# 3️⃣ Upload Logs to GCS if in Cloud Mode
# ─────────────────────────────────────────────
try:
    if not config.local_log_flag:
        log_stream = get_log_stream()
        if log_stream is not None:
            upload_log_to_gcs(log_stream.getvalue(), gcs)
            log_stream.truncate(0)
            log_stream.seek(0)
            logger.info("Logs uploaded to GCS and stream cleared.")
except Exception as e:
    logger.error("Final log upload failed: %s", e)

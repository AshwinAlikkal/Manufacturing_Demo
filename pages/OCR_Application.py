import streamlit as st
import config
from modules import gcs
from modules.logger import init_logger, get_logger, upload_log_to_gcs, get_log_stream
from modules import utils
import logging

# ─────────────────────────────────────────────
# Logger setup
# ─────────────────────────────────────────────
init_logger(config.local_log_flag)
logger = logging.getLogger("manufacturing_logger")


# ─────────────────────────────────────────────
# Streamlit page config
# ─────────────────────────────────────────────

st.set_page_config(page_title="OCR with Gemini", layout="wide")
st.title("📝 OCR Handwriting Recognition with Gemini")

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
                df_production, df_issues = utils.OCR_implementation(uploads)

            # ─────────────────────────────────────────────
            # Display Production Table
            # ─────────────────────────────────────────────
            if not df_production.empty:
                st.subheader("🏭 Production Data")
                st.dataframe(df_production, use_container_width=True)
                st.download_button(
                    label="📥 Download Production CSV",
                    data=df_production.to_csv(index=False).encode("utf-8"),
                    file_name="production_results.csv",
                    mime="text/csv"
                )
                gcs.save_dataframe(df_production, config.ocr_production_saved_path, is_local=config.local_ocr_flag)
            else:
                st.warning("⚠️ No valid production data extracted.")

            # ─────────────────────────────────────────────
            # Display Issues Table
            # ─────────────────────────────────────────────
            if not df_issues.empty:
                st.subheader("⚠️ Issues Data")
                st.dataframe(df_issues, use_container_width=True)
                st.download_button(
                    label="📥 Download Issues CSV",
                    data=df_issues.to_csv(index=False).encode("utf-8"),
                    file_name="issues_results.csv",
                    mime="text/csv"
                )
                gcs.save_dataframe(df_issues, config.ocr_issues_saved_path, is_local=config.local_ocr_flag)
            else:
                st.warning("⚠️ No valid issue data extracted.")

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

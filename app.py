# app.py  — with “Fix #1” applied
import os
import pandas as pd
import streamlit as st
import logging
from datetime import datetime

from modules import EDA_frontend, data_preprocessing, gcs
from modules.logger import (
    init_logger,
    upload_log_to_gcs,
    get_log_stream,
    get_logger,          # ← NEW
)
import config


# ─────────────────────────────────────────────────────────────
# 1.  Logger – initialise once per session and grab instance
# ─────────────────────────────────────────────────────────────
init_logger(config.local_log_flag)
logger = get_logger()                     # ← NEW (our named logger)

# keep 3rd-party noise down (use root logging module here)
logging.getLogger("matplotlib").setLevel(logging.WARNING)
logging.getLogger("matplotlib.units").setLevel(logging.ERROR)
logging.getLogger("seaborn").setLevel(logging.WARNING)

# ─────────────────────────────────────────────────────────────
# 2.  Streamlit page config
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Manufacturing Analytics",
    layout="wide",
    page_icon="🏭",
)
st.title("🏭 Manufacturing Analytics – Data Loader")

COLOR_MAP = {
    "production": "#FFF7E6",
    "issues":     "#E6F4FF",
    "demand":     "#E7FFE7",
    "engineered": "#F3E8FF",
}

# ─────────────────────────────────────────────────────────────
# 3.  Helper functions
# ─────────────────────────────────────────────────────────────
def _ensure_local(path):
    try:
        if config.local_data_flag and not os.path.exists(path):
            gcs.download(path)
            logger.info("Downloaded %s from GCS.", path)
    except Exception as e:
        logger.error("Failed to ensure local file %s: %s", path, e)
        st.error(f"Error fetching file: {path}")

def classify_and_save(upload):
    try:
        name = upload.name.lower()
        raw = upload.getvalue()

        # More robust classification — strip directories, check actual filename
        filename = os.path.basename(name)

        if "production" in filename:
            path = config.production_filepath
        elif "issue" in filename:
            path = config.issues_filepath
        elif "demand" in filename:
            path = config.demand_filepath
        else:
            st.warning(f"⚠️  **{upload.name}** skipped (need 'issue', 'production', or 'demand').")
            logger.warning("Skipped upload %s", upload.name)
            return

        gcs.write_bytes(raw, path, is_local=config.local_data_flag)
        logger.info("Saved upload %s to %s", upload.name, path)
    except Exception as e:
        logger.error("Failed to save upload %s: %s", upload.name, e)
        st.error(f"Error saving file: {upload.name}")


def header_cols(path):
    try:
        if not os.path.exists(path):
            return []
        ext = os.path.splitext(path)[1].lower()
        df0 = (
            pd.read_excel(path, nrows=0)
            if ext in (".xlsx", ".xls")
            else pd.read_csv(path, nrows=0)
        )
        return df0.columns.tolist()
    except Exception as e:
        logger.error("Failed to get headers from %s: %s", path, e)
        return []

def make_style(prod, iss, dem, eng):
    def _styler(col):
        if   col.name in prod: c = COLOR_MAP["production"]
        elif col.name in iss:  c = COLOR_MAP["issues"]
        elif col.name in dem:  c = COLOR_MAP["demand"]
        elif col.name in eng:  c = COLOR_MAP["engineered"]
        else:
            return ["" for _ in col]
        return [f"background-color:{c}" for _ in col]
    return _styler

def legend_html():
    html = []
    for key, lbl in (
        ("production", "Production"),
        ("issues", "Issues"),
        ("demand", "Demand"),
        ("engineered", "Feature – engineered"),
    ):
        html.append(
            f"<span style='display:inline-block;width:16px;height:16px;"
            f"background:{COLOR_MAP[key]};border:1px solid #ccc;margin-right:6px'></span>{lbl}"
        )
    return "  ".join(html)

def show_preview(df):
    try:
        prod, iss, dem = (
            header_cols(p)
            for p in (config.production_filepath, config.issues_filepath, config.demand_filepath)
        )
        eng = [c for c in df.columns if c not in set(prod + iss + dem)]

        styled = (
            df.head(100)
            .style
            .apply(make_style(prod, iss, dem, eng), axis=0)
            .set_table_styles([{"selector": "th", "props": [("font-weight", "bold")]}])
        )

        st.subheader("Cleaned Data Preview (top 100 rows)")
        st.write(styled)
        st.markdown(
            f"<div style='margin-top:8px;font-size:0.9rem'>{legend_html()}</div>",
            unsafe_allow_html=True,
        )
        logger.info("Displayed cleaned data preview.")
    except Exception as e:
        logger.error("Failed to show preview: %s", e)
        st.error("Failed to display data preview.")

PLOT_TASKS = [
    (config.utilization_fulfillment_plot_saved_path,    EDA_frontend.plot_utilization_fulfillment_rate),
    (config.downtime_distribution_plot_saved_path,      EDA_frontend.plot_downtime_distribution),
    (config.issues_timeline_plot_saved_path,            EDA_frontend.plot_issues_over_time),
    (config.production_downtime_saved_path,             EDA_frontend.production_downtime_over_time),
    (config.combined_production_rm_saved_path,          EDA_frontend.plot_with_shortage_markers_combined),
]

def ensure_plots(df):
    try:
        to_run = [(pth, fn) for pth, fn in PLOT_TASKS if not os.path.exists(pth)]
        if not to_run:
            logger.info("All EDA plots already exist.")
            return

        with st.spinner("Generating EDA plots…"):
            for pth, fn in to_run:
                os.makedirs(os.path.dirname(pth), exist_ok=True)
                fn(df)
                logger.info("Generated and saved EDA plot: %s", pth)

        st.toast("EDA frontend plots saved.", icon="✅")
        st.session_state["plots_done"] = True
    except Exception as e:
        logger.error("Failed to generate EDA plots: %s", e)
        st.error("Failed to generate EDA plots.")

# ─────────────────────────────────────────────────────────────
# 4.  Upload / preprocess block
# ─────────────────────────────────────────────────────────────
try:
    with st.expander(
        "📂 Upload / replace raw data (Issues, Production, Demand)",
        expanded=("cleaned_df" not in st.session_state),
    ):
        with st.form("uploader"):
            uploads = st.file_uploader(
                "Select CSV / XLSX files",
                type=["csv", "xlsx"],
                accept_multiple_files=True,
                key="up1",
            )
            submitted = st.form_submit_button("Save & Process")

        if submitted:
            if not uploads:
                st.error("Please upload at least one file.")
                logger.warning("No file uploaded.")
                st.stop()

            for f in uploads:
                classify_and_save(f)

            with st.spinner("Running preprocessing pipeline…"):
                try:
                    data_preprocessing.preprocess_and_save()
                    logger.info("Data preprocessing completed.")
                except Exception as e:
                    logger.error("Preprocessing failed: %s", e)
                    st.error("Data preprocessing failed.")
                    st.stop()

            try:
                st.session_state.cleaned_df = gcs.load_dataframe(
                    config.cleaned_path, config.local_data_flag
                )
                logger.info("Loaded cleaned dataframe from storage.")
            except Exception as e:
                logger.error("Loading cleaned data failed: %s", e)
                st.error("Failed to load cleaned data.")
                st.stop()

            st.session_state.pop("plots_done", None)
            st.success("Preprocessing complete & data cached!")
            st.rerun()
except Exception as e:
    logger.error("Error in data upload/replace section: %s", e)
    st.error("Unexpected error during data upload.")

# ─────────────────────────────────────────────────────────────
# 5.  Preview + plot generation
# ─────────────────────────────────────────────────────────────
try:
    if "cleaned_df" in st.session_state:
        show_preview(st.session_state.cleaned_df)

        if not st.session_state.get("plots_done"):
            ensure_plots(st.session_state.cleaned_df)
    else:
        st.info("Upload raw files above and click **Save & Process** to begin.")
except Exception as e:
    logger.error("Error in preview/plot section: %s", e)
    st.error("Unexpected error during preview/EDA plot generation.")

# ─────────────────────────────────────────────────────────────
# 6.  Upload logs to GCS (cloud mode)
# ─────────────────────────────────────────────────────────────
if not config.local_log_flag:
    try:
        log_stream = get_log_stream()
        if log_stream is not None:
            log_content = log_stream.getvalue()
            upload_log_to_gcs(log_content, gcs)
            log_stream.truncate(0)
            log_stream.seek(0)
            logger.info("Logs uploaded to GCS and log stream cleared.")
    except Exception as e:
        logger.error("Failed to upload logs to GCS at end of app: %s", e)

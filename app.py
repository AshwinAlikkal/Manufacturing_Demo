# app.py – Data loader → preprocessing → preview → auto-plot saver
import os
import pandas as pd
import streamlit as st

from modules import EDA_frontend, data_preprocessing, gcs
import config

# ─────────────────────────────────────
# Streamlit page setup
# ─────────────────────────────────────
st.set_page_config(page_title="Manufacturing Analytics",
                   layout="wide",
                   page_icon="🏭")
st.title("🏭 Manufacturing Analytics – Data Loader")

# ─────────────────────────────────────
# Colour palette for preview
# ─────────────────────────────────────
COLOR_MAP = {
    "production": "#FFF7E6",
    "issues":     "#E6F4FF",
    "demand":     "#E7FFE7",
    "engineered": "#F3E8FF",
}

# ─────────────────────────────────────
# Helper functions
# ─────────────────────────────────────


def _ensure_local(path):
    """If we’re in GCS mode & file missing locally → pull it down."""
    if config.local_data_flag and not os.path.exists(path):
        gcs.download(path)

def classify_and_save(upload):
    name, raw = upload.name.lower(), upload.getvalue()
    if   "issue"      in name: path = config.issues_filepath
    elif "production" in name: path = config.production_filepath
    elif "demand"     in name: path = config.demand_filepath
    else:
        st.warning(f"⚠️  **{upload.name}** skipped (need 'issue', 'production', or 'demand').")
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(raw)

def header_cols(path):
    if not os.path.exists(path):
        return []
    ext = os.path.splitext(path)[1].lower()
    df0 = pd.read_excel(path, nrows=0) if ext in (".xlsx", ".xls") else pd.read_csv(path, nrows=0)
    return df0.columns.tolist()

def make_style(prod, iss, dem, eng):
    def _styler(col):
        if   col.name in prod: c = COLOR_MAP["production"]
        elif col.name in iss:  c = COLOR_MAP["issues"]
        elif col.name in dem:  c = COLOR_MAP["demand"]
        elif col.name in eng:  c = COLOR_MAP["engineered"]
        else: return ["" for _ in col]
        return [f"background-color:{c}" for _ in col]
    return _styler

def legend_html():
    html = []
    for key, lbl in (("production","Production"),
                     ("issues","Issues"),
                     ("demand","Demand"),
                     ("engineered","Feature – engineered")):
        html.append(
            f"<span style='display:inline-block;width:16px;height:16px;"
            f"background:{COLOR_MAP[key]};border:1px solid #ccc;margin-right:6px'></span>{lbl}"
        )
    return "  ".join(html)

def show_preview(df):
    prod, iss, dem = (header_cols(p) for p in
                      (config.production_filepath, config.issues_filepath, config.demand_filepath))
    eng = [c for c in df.columns if c not in set(prod + iss + dem)]
    styled = (
        df.head(100)
          .style
          .apply(make_style(prod, iss, dem, eng), axis=0)
          .set_table_styles([{"selector":"th","props":[("font-weight","bold")]}])
    )
    st.subheader("Cleaned Data Preview (top 100 rows)")
    st.write(styled)
    st.markdown(f"<div style='margin-top:8px;font-size:0.9rem'>{legend_html()}</div>",
                unsafe_allow_html=True)

# ─────────────────────────────────────
# EDA plot generation
# ─────────────────────────────────────
PLOT_TASKS = [
    (config.utilization_fulfillment_plot_saved_path,    EDA_frontend.plot_utilization_fulfillment_rate),
    (config.downtime_distribution_plot_saved_path,      EDA_frontend.plot_downtime_distribution),
    (config.issues_timeline_plot_saved_path,            EDA_frontend.plot_issues_over_time),
    (config.production_downtime_saved_path,             EDA_frontend.production_downtime_over_time),
    (config.combined_production_rm_saved_path,          EDA_frontend.plot_with_shortage_markers_combined),
]

def ensure_plots(df):
    to_run = [ (pth, fn) for pth, fn in PLOT_TASKS if not os.path.exists(pth) ]
    if not to_run:
        return
    with st.spinner("Generating EDA plots…"):
        for pth, fn in to_run:
            os.makedirs(os.path.dirname(pth), exist_ok=True)
            fn(df)
    st.toast("EDA frontend plots saved.", icon="✅")
    st.session_state["plots_done"] = True

# ─────────────────────────────────────
# 1️⃣  Upload / replace raw data
# ─────────────────────────────────────
with st.expander("📂 Upload / replace raw data (Issues, Production, Demand)",
                 expanded=("cleaned_df" not in st.session_state)):
    with st.form("uploader"):
        uploads = st.file_uploader(
            "Select CSV / XLSX files",
            type=["csv","xlsx"],
            accept_multiple_files=True,
            key="up1"
        )
        submitted = st.form_submit_button("Save & Process")

    if submitted:
        if not uploads:
            st.error("Please upload at least one file.")
            st.stop()

        for f in uploads:
            classify_and_save(f)

        with st.spinner("Running preprocessing pipeline…"):
            data_preprocessing.preprocess_and_save()

        st.session_state.cleaned_df = gcs.load_dataframe(config.cleaned_path, config.local_data_flag)
        # 🔁 Backend EDA: auto-save plots per line
        # with st.spinner("Running backend EDA analysis…"):
        #     df = st.session_state.cleaned_df
        #     lines = df['Production Line'].dropna().unique()
        #     for line in lines:
        #         path = f'EDA_plots/Backend_Plots/{line}/{line}_combined_analysis.png'
        #         os.makedirs(os.path.dirname(path), exist_ok=True)
        #         EDA_backend.create_combined_linewise_figure(df, line=line, save_path=path)
        #     st.toast("Backend EDA plots saved.", icon="🧠")

        st.session_state.pop("plots_done", None)
        st.success("Preprocessing complete & data cached!")
        st.rerun()

# ─────────────────────────────────────
# 2️⃣  Preview & ensure plots
# ─────────────────────────────────────
if "cleaned_df" in st.session_state:
    show_preview(st.session_state.cleaned_df)

    if not st.session_state.get("plots_done"):
        ensure_plots(st.session_state.cleaned_df)
else:
    st.info("Upload raw files above and click **Save & Process** to begin.")

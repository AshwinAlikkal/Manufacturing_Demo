# pages/2_Report_Creation.py  – full replacement (no chat)
import os
from datetime import date

import streamlit as st
from streamlit_pdf_viewer import pdf_viewer
import pandas as pd

from modules import utils, EDA_backend, prompts       
import config

# ─────────────────────────────────────────────
# Streamlit page
# ─────────────────────────────────────────────
st.set_page_config(page_title="Report Creation",
                   page_icon="📝", layout="wide")
st.title("📝 Manufacturing Analytics – Report Creator")

# ─────────────────────────────────────────────
# 1) Parameter picker
# ─────────────────────────────────────────────
with st.expander("⚙️ Report Parameters", expanded=True):
    c1, c2 = st.columns(2)
    with c1:
        report_date = st.date_input("Select Report Date", date.today())
    with c2:
        shift = st.selectbox("Select Shift", ["Day", "Night"])

    # initialise session flags once
    if "report_generated" not in st.session_state:
        st.session_state.report_generated = False
    if "report_path" not in st.session_state:
        st.session_state.report_path = None

    # ───────── Generate button ────────────────
    if st.button("🚀 Generate / View Report"):
        with st.spinner("Working…"):
            # build the target path first
            safe_date = report_date.strftime("%Y-%m-%d")
            out_dir   = "Reports_Created"
            out_path  = os.path.join(out_dir, f"Report_{safe_date}_{shift}.pdf")

            # 1) If already exists → just use it
            if os.path.exists(out_path):
                st.session_state.report_path  = config.report_path
                st.session_state.report_generated = True
                st.toast("✔️ Re-using existing PDF", icon="📄")

            # 2) Else run the heavy pipeline
            else:
                # 🔁 Backend EDA plots triggered from here
                df = pd.read_csv(config.cleaned_path)
                lines = df['Production Line'].dropna().unique()
                for line in lines:
                    path = f'EDA_plots/Backend_Plots/{line}/{line}_combined_analysis.png'
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    EDA_backend.create_combined_linewise_figure(
                        df=df,
                        line=line,
                        save_path=path,
                        date=report_date.strftime("%Y-%m-%d"),
                        shift=shift
                    )

                # 🧠 Continue with report logic
                prod_issue = utils.generate_manufacturing_analysis()
                deficit    = utils.run_recovery_text_output(report_date, shift)
                metrics    = pd.read_csv(config.linewise_pivot_data_filepath).to_string()

                user_prompt = prompts.prompt_generation(prod_issue, deficit, metrics, report_date, shift)
                md_report = utils.build_report_string(user_prompt)

                saved_pdf = utils.pdf_creation(md_report)
                st.session_state.report_path = saved_pdf
                st.session_state.report_generated = True
                st.toast("✅ PDF generated", icon="✅")

        st.success("Report ready!")

# ─────────────────────────────────────────────
# 2) Show PDF viewer + Download
# ─────────────────────────────────────────────
if st.session_state.get("report_generated") and st.session_state.get("report_path"):
    st.header("📄 Report Preview")
    pdf_viewer(st.session_state.report_path, width=900, height=720)

    with open(st.session_state.report_path, "rb") as f:
        st.download_button("Download PDF", f,
                           file_name=os.path.basename(st.session_state.report_path),
                           mime="application/pdf")
else:
    st.info("Select parameters and click **Generate / View Report**.")

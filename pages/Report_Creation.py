# pages/2_Report_Creation.py – GCS/local compliant version
import os
from datetime import date
import streamlit as st
from streamlit_pdf_viewer import pdf_viewer
import pandas as pd

from modules import utils, EDA_backend, prompts, gcs
import config

# ─────────────────────────────────────────────
# Streamlit page
# ─────────────────────────────────────────────
st.set_page_config(page_title="Report Creation",
                   page_icon="📝", layout="wide")
st.title("📝 Manufacturing Analytics – Report Creator")

# ─────────────────────────────────────────────
# 1️⃣ Parameter picker
# ─────────────────────────────────────────────
with st.expander("⚙️ Report Parameters", expanded=True):
    c1, c2 = st.columns(2)
    with c1:
        report_date = st.date_input("Select Report Date", date.today())
    with c2:
        shift = st.selectbox("Select Shift", ["Day", "Night"])

    if "report_generated" not in st.session_state:
        st.session_state.report_generated = False
    if "report_path" not in st.session_state:
        st.session_state.report_path = None

    if st.button("🚀 Generate / View Report"):
        with st.spinner("Working…"):
            safe_date = report_date.strftime("%Y-%m-%d")
            out_path = f"Reports_Created/Report_{safe_date}_{shift}.pdf"

            # ✅ Use existing local report if allowed
            if config.local_report_flag and os.path.exists(out_path):
                st.session_state.report_path = out_path
                st.session_state.report_generated = True
                st.toast("✔️ Re-using existing PDF", icon="📄")
            else:
                # 1️⃣ Load cleaned data
                df = gcs.load_dataframe(config.cleaned_path, config.local_data_flag)
                lines = df['Production Line'].dropna().unique()

                # 2️⃣ Save backend plots to correct config paths
                paths = {
                    "Line1": config.line1_combined_analysis_path,
                    "Line2": config.line2_combined_analysis_path,
                    "Line3": config.line3_combined_analysis_path
                }
                for line in lines:
                    if line in paths:
                        EDA_backend.create_combined_linewise_figure(
                            df=df,
                            line=line,
                            save_path=paths[line],
                            date=safe_date,
                            shift=shift
                        )

                # 3️⃣ Generate report
                prod_issue = utils.generate_manufacturing_analysis()
                deficit = utils.run_recovery_text_output(report_date, shift)
                metrics_df = gcs.load_dataframe(config.linewise_pivot_data_filepath, config.local_data_flag)
                metrics = metrics_df.to_string()

                user_prompt = prompts.prompt_generation(prod_issue, deficit, metrics, report_date, shift)
                md_report = utils.build_report_string(user_prompt)

                saved_pdf = utils.pdf_creation(md_report, save_path=out_path)
                st.session_state.report_path = out_path
                st.session_state.report_generated = True
                st.toast("✅ PDF generated", icon="✅")

        st.success("Report ready!")

# ─────────────────────────────────────────────
# 2️⃣ Show PDF viewer + Download
# ─────────────────────────────────────────────
# ─────────────────────────────────────────────
# 2️⃣ Show PDF viewer + Download
# ─────────────────────────────────────────────
if st.session_state.get("report_generated") and st.session_state.get("report_path"):
    st.header("📄 Report Preview")

    pdf_path = st.session_state.report_path

    if config.local_report_flag:
        # ✅ Local mode — use the actual file path directly
        pdf_viewer(pdf_path, width=900, height=720)
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
    else:
        # ✅ GCS mode — fetch from bucket and store temp file
        pdf_bytes = gcs.read_bytes(pdf_path, is_local=False)
        tmp_path = f"/tmp/{os.path.basename(pdf_path)}"
        with open(tmp_path, "wb") as f:
            f.write(pdf_bytes)
        pdf_viewer(tmp_path, width=900, height=720)

    st.download_button("Download PDF", pdf_bytes,
                       file_name=os.path.basename(pdf_path),
                       mime="application/pdf")
else:
    st.info("Select parameters and click **Generate / View Report**.")




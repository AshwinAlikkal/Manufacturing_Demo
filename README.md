# 🏭 Manufacturing Analytics Dashboard

A modular, Streamlit-based application for real-time data analysis, visualization, and AI-powered reporting for manufacturing units. Built with flexible support for both **local** and **Google Cloud Storage (GCS)** environments, this app helps plant managers and analysts optimize operations using intelligent visual and textual insights.

---

## 🚀 Features

### 📥 Data Upload & Preprocessing
- Upload Issues, Production, and Demand datasets (`.csv` or `.xlsx`).
- Intelligent classification and saving.
- Data preprocessing pipeline with cleaning and merging logic.
- Cleaned data is cached and reused until refreshed.

### 📊 EDA Visualizations (Plotly)
- Utilization vs Shift (boxplot)
- Fulfillment Rate over Time
- Downtime Distributions (box, bar, heatmap)
- Issue Timelines (bubble chart)
- Production vs Downtime per shift
- Raw Material Inventory & Shortage Alerts

### 📄 PDF Report Generation
- Line-wise combined backend plots (saved as images)
- AI-generated summary analysis using OpenAI/Hugging Face
- Optimization-based recovery scheduling
- Markdown-to-PDF conversion with in-app preview and download
- Report saved to GCS or local depending on flags

### ☁️ GCS Support
- Seamless switching between local and cloud environments
- Support for data, logs, plots, and reports in GCS
- Dynamic download-on-demand for cloud files

### 📝 Smart Logging
- Contextual logs with in-memory (GCS mode) or file-based (local) support
- Logs automatically uploaded to GCS in cloud mode

---

## 🗂️ Project Structure
manufacturing-analytics/
├── app.py                            # Main page: Data Loader & Preprocessor
├── config.py                         # Central config: paths, flags, model settings
├── requirements.txt                  # Python dependencies
├── README.md                         # Project documentation (you’re reading this!)
│
├── Logs/                             # Local logs (if enabled)
│   └── YYYYMMDD/ManufacturingLog.txt
│
├── Reports_Created/                  # Locally saved reports (PDFs)
│   └── Report_YYYY-MM-DD_Shift.pdf
│
├── pages/                            # Streamlit multipage support
│   ├── 2_Report_Creation.py          # Automated PDF generation with OpenAI/HF
│   └── Visualizations.py             # Interactive Plotly dashboards
│
├── modules/                          # Core logic
│   ├── data_preprocessing.py         # Data cleaning, merging logic
│   ├── EDA_frontend.py               # Plotting functions used in `app.py`
│   ├── EDA_backend.py                # Line-wise backend plot creation
│   ├── gcs.py                        # GCS upload/download helpers
│   ├── logger.py                     # Stream/file logger setup + GCS upload
│   ├── prompts.py                    # Prompt templates for OpenAI/HF LLM
│   ├── utils.py                      # Report logic: analysis, markdown, PDF
│
├── EDA_plots/                        # Saved backend plots
│   └── Backend_Plots/
│       ├── Line1/line1_combined_analysis.png
│       ├── Line2/line2_combined_analysis.png
│       └── Line3/line3_combined_analysis.png


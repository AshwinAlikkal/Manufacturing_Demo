# Data local plots saved path
issues_filepath = "Data/Source_Data/Issues_Data/Issues_downtime_rawmaterial_data.xlsx"
production_filepath = "Data/Source_Data/Issues_Data/Production_data.xlsx"
demand_filepath = "Data/Source_Data/Issues_Data/Demand_data.xlsx"
cleaned_path = "Data/Final_Data/Cleaned_Data/cleaned_data.csv"
merged_data_filepath = "Data/Source_Data/Merged_Data/merged_data.csv"
linewise_pivot_data_filepath = "Data/Final_Data/Data_For_AI/linewise_pivot_data.csv"
ocr_production_saved_path = "Data/OCR_Data/Production_OCR.csv"
ocr_issues_saved_path = "Data/OCR_Data/Issues_OCR.csv"
production_plan_filepath = "Data/Reported_plans/Production_plan.csv"
line_summary_filepath = "Data/Reported_plans/line_summary_plan.csv"

# EDA local plots saved path
utilization_fulfillment_plot_saved_path = 'EDA_plots/Frontend_Plots/Utilization_Fulfillment/linewise_utilization_fulfillment_downtime.png'
downtime_distribution_plot_saved_path = 'EDA_plots/Frontend_Plots/Downtime_distribution/linewise_issue_downtime.png'
issues_timeline_plot_saved_path = 'EDA_plots/Frontend_Plots/Issues_Timeline/issues_timeline_by_line.png'
production_downtime_saved_path = 'EDA_plots/Frontend_Plots/Production_vs_Downtime/prod_downtime_issues_by_line_shift.png'
combined_production_rm_saved_path = 'EDA_plots/Frontend_Plots/Inventory_Shortages/Combined_Production_RawMaterial_Shortages.png'

## EDA local backend files
line1_combined_analysis_path = "EDA_plots/Backend_Plots/Line1/line1_combined_analysis.png"
line2_combined_analysis_path = "EDA_plots/Backend_Plots/Line2/line2_combined_analysis.png"
line3_combined_analysis_path = "EDA_plots/Backend_Plots/Line3/line3_combined_analysis.png"

# GCS bucket details
GCS_BUCKET_NAME = "terasaka_demo_bucket"

# Flags
local_data_flag = False
local_eda_flag = False
local_report_flag = False
local_log_flag = False
local_ocr_flag = False
line_summary_flag = False
production_plan_flag = False
## Model
USE_OPENAI = True
huggingface_model = "google/gemma-3-27b-it"
hugging_face_temperature=0.0
gpt_model = "gpt-4.1-mini"
ocr_model = "gemini-1.5-flash"


#Logging
log_file_name = "Logs/manufacturing_analysis.txt"

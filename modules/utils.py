import os
import numpy as np
import markdown
from xhtml2pdf import pisa
import pandas as pd
from openai import OpenAI
import base64
from huggingface_hub import InferenceClient, login
from modules import prompts,gcs
from math import ceil
from scipy.optimize import linprog
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import config

from dotenv import load_dotenv
import os

load_dotenv()  # Load from .env

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")

def encode_image(path):
    """
    Encode an image file to a base64 string.
    Args:
        path (str): Path to the image file.
    """
    image_bytes = gcs.read_bytes(path, config.local_eda_flag)
    return f"data:image/png;base64,{base64.b64encode(image_bytes).decode('utf-8')}"


def generate_manufacturing_analysis():
    """
    Generate manufacturing analysis using OpenAI or Hugging Face API.
    Args:
        None
    """
    image_paths = [
        config.line1_combined_analysis_path,
        config.line2_combined_analysis_path,
        config.line3_combined_analysis_path
        ]
 
    titles = [
        "Plot 1 : Line 1 Combined EDA",
        "Plot 2 : Line 2 Combined EDA",
        "Plot 3 : Line 3 Combined EDA",
    ]

    manufacturing_system_prompt = prompts.manufacturing_system_prompt
    combined_analysis = ""
    

    if config.USE_OPENAI:
        client = OpenAI(api_key = OPENAI_API_KEY)
 
        for title, path in zip(titles, image_paths):
            encoded_image = encode_image(path)
    
            messages = [
                {"role": "system", "content": manufacturing_system_prompt},
                {"role": "user", "content": [
                    {"type": "text", "text": title},
                    {"type": "image_url", "image_url": {"url": encoded_image}}
                ]}
            ]
    
            response = client.chat.completions.create(
                model = config.gpt_model,
                messages = messages
                #max_tokens=config.hugging_face_max_tokens,
            )
    
            analysis = response.choices[0].message.content
            combined_analysis += f"\n\n### {title}\n{analysis}"
            
    else: 
        login(HUGGINGFACE_API_KEY)
        client = InferenceClient(config.huggingface_model, token=HUGGINGFACE_API_KEY)
        for title, path in zip(titles, image_paths):   
            encoded_image = encode_image(path)
    
            messages = [
                {"role": "system", "content": manufacturing_system_prompt},
                {"role": "user", "content": [
                    {"type": "text", "text": title},
                    {"type": "image_url", "image_url": {"url": encoded_image}}
                ]}
            ]
    
            response = client.chat.completions.create(
                model = config.huggingface_model,
                messages = messages
            )
    
            analysis = response.choices[0].message.content
            combined_analysis += f"\n\n### {title}\n{analysis}"

    return combined_analysis


 
# --- Optimizaion tool ---
def run_recovery_text_output(start_date, start_shift):
    """
    1) Load the CSV and timestamp each shift
    2) Sum deficits from (start_date, start_shift) onward
    3) Try to repay in one day; if not, compute a minimal multi-day plan
    4) Return a single text block you can drop into a prompt.

    Args:
        path (str): Path to the CSV file.
        start_date (str): Start date in 'YYYY-MM-DD' format.
        start_shift (str): Start shift, either 'Day' or 'Night'.
    """
    # --- 1) load & timestamp ---
    df = gcs.load_dataframe(config.cleaned_path, config.local_data_flag)
    df['Date'] = pd.to_datetime(df['Date']) 
    df['shift_time'] = np.where(
        df['Shift']=='Day',
        df['Date'] + pd.Timedelta(hours=12),
        df['Date'] + pd.Timedelta(hours=20)
    )
    df = df.sort_values('shift_time').reset_index(drop=True)
 
    # --- 2) Define cutoff ---
    cut = pd.to_datetime(start_date) + (
        pd.Timedelta(hours=12) if start_shift=='Day'
        else pd.Timedelta(hours=20)
    )
 
    # --- 3) Split data ---
    baseline = df[df['shift_time'] < cut]
    window   = df[df['shift_time'] >= cut]
 
    # Total deficit to recover
    D = window['Production_Deficit'].sum()
 
    # D = 200
    # Baseline avg hours (pre-cutoff) and rates (post-cutoff)
    avg_time  = baseline.groupby('Production Line')['Machine Operation Time (hrs)'].mean()
    prod_rate = window.groupby('Production Line')['Production Rate (units/hr)'].mean()
 
    # Align lines
    lines = sorted(set(avg_time.index).intersection(prod_rate.index))
    avg   = avg_time.loc[lines].values
    rate  = prod_rate.loc[lines].values
 
    # Common LP ingredients for s_i = extra hours
    bounds = [(max(0, 6 - ai), max(0, 10 - ai)) for ai in avg]
    c       = -rate
    A_ub    = rate.reshape(1, -1)
    b_ub    = [D]
 
    # --- 4) Single-day LP ---
    sol = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method='highs')
    if sol.success and (rate @ sol.x) >= D - 1e-6:
        s_opt    = sol.x
        h_opt    = avg + s_opt
        produced = float((rate * s_opt).sum())
 
        sched = pd.DataFrame({
            'Production Line': lines,
            'Avg Hours':       avg,
            'Opt Hours':       h_opt,
            '% Increase':      100 * s_opt / avg,
            'Extra Prod':      rate * s_opt
        })
        sched_date = (pd.to_datetime(start_date) + pd.Timedelta(days=1)).date()
 
        out = [
            f"Total Deficit from {start_date} {start_shift} shift: {D:.1f} units",
            f"\nSingle-Day Schedule for {sched_date}:",
            sched.to_string(index=False, float_format="%.2f"),
            f"\nTotal Produced Against Deficit: {produced:.1f} units"
        ]
        return "\n\n".join(out)
 
    # --- 5) Multi-day fallback with rate-proportional distribution ---
    # Compute minimal days under max 10 hr cap
    max_daily = ((10 - avg) * rate).sum()
    days      = ceil(D / max_daily)
    daily_def = D / days
 
    # Distribute the per-day deficit across lines in proportion to their rates:
    #   s_prop[i] = daily_def * rate[i] / sum(rate**2)
    # so that sum(rate * s_prop) == daily_def
    denom = np.dot(rate, rate)
    s_prop = daily_def * rate / denom
 
    # Final hours clipped into [6, 10]
    h_daily = np.clip(avg + s_prop, 6, 10)
 
    sched = pd.DataFrame({
        'Production Line':      lines,
        'Avg Hours':            avg,
        'Daily Hours required': h_daily,
        '% Increase':           100 * (h_daily - avg) / avg
    })
 
    out = [
        f"Total Deficit from {start_date} {start_shift} shift: {D:.1f} units",
        f"\nRequires minimum {days} days to recover deficit.",
        "\nDaily Schedule(Shiftwise):",
        sched.to_string(index=False, float_format="%.2f")
    ]
    return "\n\n".join(out)

def build_report_string(prompt):

    """
    1) Generate a markdown report string using OpenAI.
    Args:
        prompt (str): The prompt to generate the report string.
    """

    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=config.gpt_model,
        messages=[
            {"role": "system", 
             "content": prompt}
        ],
        temperature=0.0,
        #max_tokens=2000
    )
    return response.choices[0].message.content


# def pdf_creation(md_content, save_path):

#     """
#     1. Convert markdown to HTML
#     2. Add basic CSS for styling
#     3. Save the HTML as a PDF file
#     Args:
#         md_content (str): The markdown content to convert to PDF.
#     """
#     if not save_path:
#         raise ValueError("PDF creation requires an explicit save_path.")
#     html_content = markdown.markdown(md_content, extensions=['extra'])
#     html_full = prompts.build_html_content(html_content)
#     from modules import gcs
#     gcs.save_pdf(html_full, save_path, config.local_report_flag)
#     return save_path

def pdf_creation(md_content, save_path):
    if not save_path:
        raise ValueError("PDF creation requires an explicit save_path.")

    from xhtml2pdf import pisa
    from io import BytesIO
    from modules import gcs

    html_content = markdown.markdown(md_content, extensions=['extra'])
    html_full = prompts.build_html_content(html_content)

    output = BytesIO()
    pisa_status = pisa.CreatePDF(html_full, dest=output)
    output.seek(0)

    if config.local_report_flag:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "wb") as f:
            f.write(output.read())
        print(f"✅ PDF saved locally: {save_path}")
    else:
        gcs.upload_blob_from_bytes(
            content=output.read(),
            destination_blob_name=save_path,
            content_type="application/pdf"
        )
        print(f"✅ PDF uploaded to GCS: {save_path}")

    return save_path


    


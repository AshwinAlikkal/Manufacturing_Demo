import os
import numpy as np
import markdown
from xhtml2pdf import pisa
import pandas as pd
from openai import OpenAI
import base64
from huggingface_hub import InferenceClient, login
from modules import prompts
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
    with open(path, "rb") as f:
        return f"data:image/png;base64,{base64.b64encode(f.read()).decode('utf-8')}"


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
    df = pd.read_csv(config.cleaned_path, parse_dates=['Date'])
    df['shift_time'] = np.where(
        df['Shift']=='Day',
        df['Date'] + pd.Timedelta(hours=12),
        df['Date'] + pd.Timedelta(hours=20)
    )
    df = df.sort_values('shift_time').reset_index(drop=True)

    # --- 2) cut window from start shift onward ---
    d = pd.to_datetime(start_date)
    cut = d + (pd.Timedelta(hours=12) if start_shift=='Day'
               else pd.Timedelta(hours=20))
    window = df[df['shift_time'] >= cut]

    D = window['Production_Deficit'].sum()
    avg_time  = window.groupby('Production Line')['Machine Operation Time (hrs)'].mean()
    prod_rate = window.groupby('Production Line')['Production Rate (units/hr)'].mean()

    lines = avg_time.index.tolist()
    avg   = avg_time.values
    rate  = prod_rate.values

    # --- 3a) single‐day LP ---
    c      = -rate
    A_ub   = rate.reshape(1, -1)
    b_ub   = [D]
    bounds = [(0, max(0, 10 - a)) for a in avg]

    sol = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method='highs')
    if sol.success:
        s = sol.x
        produced = float((rate * s).sum())
        if produced >= D - 1e-6:
            # build schedule table
            h_opt = avg + s
            sched = pd.DataFrame({
                'Production Line':     lines,
                'Avg Hours':           avg,
                'Opt Hours':           h_opt,
                '% Increase':          100*s/avg,
                'Extra Prod':          rate*s
            })
            # compute recovery date = day after start_date
            sched_date = (pd.to_datetime(start_date) + pd.Timedelta(days=1)).date()

            out = []
            out.append(f"Total Deficit from {start_date} {start_shift} shift: {D:.1f} units")
            out.append(f"\nSingle-Day Schedule for {sched_date}:")
            out.append(sched.to_string(index=False, float_format="%.2f"))
            out.append(f"\nTotal Produced Against Deficit: {produced:.1f} units")
            return "\n\n".join(out)

    # --- 3b) multi‐day fallback ---
    max_daily = ((10 - avg) * rate).sum()
    days      = ceil(D / max_daily)
    daily_def = D / days
    extra_h   = daily_def / rate.sum()

    sched = pd.DataFrame({
        'Production Line':      lines,
        'Avg Hours':            avg,
        'Daily Hours required': avg + extra_h,
        '% Increase':           100*extra_h/avg
    })

    out = []
    out.append(f"Total Deficit from {start_date} {start_shift} shift: {D:.1f} units")
    out.append(f"\nRequires minimum {days} days to recover deficit.")
    out.append("\nDaily Schedule:")
    out.append(sched.to_string(index=False, float_format="%.2f"))
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


def pdf_creation(md_content):

    """
    1. Convert markdown to HTML
    2. Add basic CSS for styling
    3. Save the HTML as a PDF file
    Args:
        md_content (str): The markdown content to convert to PDF.
    """

    # 2. Convert markdown to HTML
    html_content = markdown.markdown(md_content, extensions=['extra'])
    
    # 3. Optional: Add basic CSS for styling
    html_full = prompts.build_html_content(html_content)
 
    os.makedirs(os.path.dirname(config.report_path), exist_ok=True)
    with open(config.report_path, "wb") as f:
        pisa.CreatePDF(html_full, dest=f)
    return config.report_path
    


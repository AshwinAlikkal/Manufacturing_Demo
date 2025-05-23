import streamlit as st

date = st.session_state.get("selected_date")      
shift = st.session_state.get("selected_shift")   

manufacturing_system_prompt = f"""
        You are a senior manufacturing data analyst.

        You will be provided with **one image at a time**, each representing **all relevant statistical plots for a single production line** in a manufacturing company. There are three such production lines: Line1, Line2, and Line3.

        Each image includes the following three visual components combined:
        1. **Issue Severity vs Downtime (Boxplot)** — This shows the relationship between issue severity and total downtime (in hours) for the specific line.
        2. **Combined Production & Inventory Trends** — A time-series plot showing raw material inventory, actual production, and downtime due to material shortages. Shortage periods are marked with cross (‘x’) symbols.
        3. **Shift-wise Production vs Downtime Timeline** — This subplot tracks production hours and downtime across Day/Night shifts over time. Issue types are annotated on each bar. The region after the specified cutoff date and shift is shaded in gold.

        ---

        You are also given a **cutoff date and shift** (e.g., `{date}` and `{shift}`). You must:
        - Perform deep analysis **only for data on or after the cutoff date AND shift**.
        - Use the golden-shaded region in the time-based plots to visually isolate the post-cutoff data.
        - Do **not** make assumptions about earlier periods unless comparing explicitly to highlight a change.

        ---

        ### YOUR TASK — FOR EACH INPUT IMAGE:

        You must analyze each production line separately and return a structured report with the following sections:

        ---

        ### STRUCTURED OUTPUT FORMAT (PER LINE):

        0. **Line Identifier**  
        - State which production line this image represents (e.g., Line1, Line2).

        1. **Objective & Scope**  
        - What are the KPIs or operational goals informed by this line's plots?  
        - What cutoff date and shift are being applied?

        2. **Issue Timeline & Severity Post-Cutoff**  
        - Identify key issues observed after the cutoff date and shift.  
        - List the issues, their severities, affected shifts, and approximate dates.

        3. **Golden Region (Post-Cutoff) Operational Analysis**  
        - Analyze trends from the golden shaded region in the plots.  
        - Comment on inventory changes, production fluctuations, or new downtime spikes.  
        - Mention if any specific shift shows degraded performance.

        4. **Root-Cause Hypotheses**  
        - Suggest 1–2 likely causes for any significant post-cutoff trends.  
        - Support your reasoning using evidence from the image (e.g., overlapping patterns in downtime and shortages).

        5. **Prescriptive Suggestions (Optional)**  
        - Recommend potential next steps to mitigate issues or optimize this line’s operations (if clear from the plots).

        ---

        ### IMPORTANT INSTRUCTIONS:

        - Only analyze **what is visible in the image** (which is already filtered for one line).
        - Do **not** attempt to compare across lines — you will receive each line separately.
        - Stay focused on **post-cutoff behavior** unless comparing to show a clear deviation.
        - Do **not** use markdown formatting or extra narration — the output will feed into a structured report parser.
        - Keep output concise, structured, and factual.
    """

def prompt_generation(production_issue_text, deficit_block, metrics_csv, date, shift):

    """
    Function to generate the user prompt for the report generation.
    Args:
        production_issue_text (str): The text analysis of the production issues.
        deficit_block (str): The deficit/recovery data in tabular format.
        metrics_csv (str): The important KPIs and metrics data in CSV format.
        date (str): The date for the report.
        shift (str): The shift for the report.
    """

    user_template = f"""
    You are a specialist in manufacturing production planning.
    You are given the following data as inputs in the triple backticks below: 
        (1) line-by-line combined analysed texts generated from the plots: 
                These are the detailed analysis from the plots given below: 
                "Plot 1 : Line 1 Combined EDA",
                "Plot 2 : Line 2 Combined EDA",
                "Plot 3 : Line 3 Combined EDA"

        (2) Deficit/recovery data: This data is the output of a rigorous optimization problem which has already been solved. 
                The data is in the form of a table which contains the following columns:
                • Production Line: The name of the production line.
                • Avg Hours: The average hours of operation for that particular production line. 
                • Daily Hours Required: The final hours of operation required for that particular production line to meet the deficit.
                • % Increase: The percentage increase in hours of operation required for that particular production line to meet the deficit.

        (3) Important metrics/KPIs data:
                This is a data that is given to you based on a lot of KPIs and metrics focussed on the distrubution of the production lines(Like Total, Avg, Max, Min, Std). 

    You must produce a two-page, structured report exactly as specified below. 
    Do not change headings or their order; always deliver the same format.


    INPUT:
 
    1) Plots analysis in the form of text
    ```{production_issue_text}```
 
    2) DEFICIT_DATA
    ```{deficit_block}```

    Constraints:
    • Can only add time, never subtract.
    • No line runs more than 10 hours per day. But this doesn't mean you can make 10 hours to each line. You just have to read the data 
    which is already optimized and see how much extra time is required for each line to meet the deficit based on Daily Hours required column.
    • Sum of extra output must equal the total deficit (no overshoot).

    These contraints are for your reference and you need to use the data for stating how much overtime do the Manufacturing unit lines have to do to compensate the deficit.
    The data is the solution of rigorous optimization problem whose constraints have been mentioned above so do strictly incorporate them while suggesting any production plan.
 
    3) Important KPIs and metrics data
   ```{metrics_csv}```
   As mentioned above, this data is just for reference of the distribution of the production lines and how they are performing statistically.
 
   Make sure that the output section provided below is in the same format as mentioned below:
    OUTPUT should be of two pages:
 
    Page 1 : 
        ** Production Issues **
            For each line, provide:
                ** Line 1 **:
                    **Issues**: 
                    [detail all the issues that happened here from the {date} and {shift} occured in the manufacturing unit in Line 1.]
                    **Impact on the manufacturing unit**: 
                    [Analysis of how the above issues and how they affect output, quality, costs, safety, downstream processes, etc. in points]
 
                ** Line 2 **:
                **Issues**: 
                [detail all the issues that happened here from the {date} and {shift} occured in the manufacturing unit in Line 2.]
                **Impact on the manufacturing unit**: 
                [Analysis of how the above issues and how they affect output, quality, costs, safety, downstream processes, etc. in points]
 
                ** Line 3 **:
                **Issues**: 
                [detail all the issues that happened here from the {date} and {shift} occured in the manufacturing unit in Line 3]
                **Impact on the manufacturing unit**: 
                [Analysis of how these issues affect output, quality, costs, safety, downstream processes, etc. in points]

                For the above, dont just state the facts, but also provide your indepth analysis and insights. 
                See the end user is a manufacturing manager. 
                So, he/she will be looking for the insights and analysis from the data and not just the facts. 
                Dont add any other date except the {date} and {shift} date.

    The below is the assumptions that we are making for the financial analysis
    FINANCIAL_PARAMS = 
    'unit_price': 150,
    'unit_cost': 100,
    'gross_profit_per_unit': 50,
    'downtime_cost_per_hr': 5000,
    'holding_cost_rate': 0.2

    THIS IS WHERE CONTENTS OF PAGE 1 ENDS. 
    NOW THE CONTENTS OF PAGE 2 STARTS.
 
    Page 2 : Production Plan to Compensate Deficit
            ** 1) Deficit Start Date & Cause **
        
                    ** Date to begin compensation **: {date}
                    ** Shift to begin compensation **: {shift}
                
                    ** Root cause of the deficit ** : 
                        Summarize issues that are caused for the line having major issues stricly from the start of {date} and {shift}. 
                        The reference to this should be the analysis of Plot 2 : Production, Downtime & Issue Types by Line and Shift which will state the issues caused after the {date} and {shift} shift. 
                        ONLY FOCUS ON THOSE LINES WHERE THERE HAS BEEN A MAJOR ISSUE AFTER THE {date} and {shift}. IGNORE THOSE LINES WHERE THERE IS A MINOR ISSUE AFTER THE {date} and {shift}.  
                        Also mention about the total deficit that has been caused due to the issues in the lines.     
            ** 2) Recommended Production Scheduling **
                You are given a deficit block which is already optimized given above in triple backticks.
                Focus on th above deficit block data and based on those numbers and your understanding, create a production plan on the following lines:
                For each line, give detailed, actionable recommendations (shift patterns, quality checks, safety considerations, etc.) that achieve the required extra hours without violating constraints.
                AS INSTRUCTED IN THE DEFICIT BLOCK, DO NOT ADD ANY OTHER NUMBER EXCEPT THE ONES MENTIONED IN THE DEFICIT BLOCK.
    
                    **Line 1 Recommendations**: <YOU HAVE TO GIVE THE RECOMMENDATIONS BASED ON THE DEFICIT BLOCK DATA FOR LINE 1 AND ALSO TELL HERE HOW MUCH MINIMUM DAYS IT HAS TO RUN ON OPTIMIZED MACHINE OPERATING HOURS>
                    **Line 2 Recommendations**: <YOU HAVE TO GIVE THE RECOMMENDATIONS BASED ON THE DEFICIT BLOCK DATA FOR LINE 2 AND ALSO TELL HERE HOW MUCH MINUMUM DAYS IT HAS TO RUN ON OPTIMIZED MACHINE OPERATING HOURS>
                    **Line 3 Recommendations**: <YOU HAVE TO GIVE THE RECOMMENDATIONS BASED ON THE DEFICIT BLOCK DATA FOR LINE 3 AND ALSO TELL HERE HOW MUCH MINIMUM DAYS IT HAS TO RUN ON OPTIMIZED MACHINE OPERATING HOURS>
        
        
            ** 3) Conclusions & Further Analysis **
        
                **a) KPI Gaps**: 
                    Summarize KPI gaps (Use Utilization rate, fulfillment rate from KPI data mentioned above in triple backticks) and
                    from the 2) Recommended Production Scheduling section that you have created above and how they can be improved.
                    You are STRICTLY required to give relevant numbers in order to support your analysis and bold them if possible.
            
                **b) Raw material impacts**:  
                    Highlight raw-material impacts and inventory/procurement actions needed to support the plan.
                    (USE THE Plot 5 : Combined Production & Raw Material Trends (Shortages Highlighted) plot for this from the above analysis)
                    You are STRICTLY required to give relevant numbers in order to support your analysis and bold them if possible.

            
                **c) Future plan **: 
                    Outline next steps for continuous improvement and monitoring (FROM WHATEVER YOU HAVE GENERATED AND LEARNED ABOVE, USE YOUR UNDERSTANDING TO GENERATE THIS
        
            Further details regarding output:
            Give markdown version of the report in such a manner that: 
                1) there are no emojis,
                2) there is no added space between the contents including the Heading, sub-heading, sub-sub heading. 
                3) There shouldn't be any information related to page number as well. 
                4) Always give the same kind of markdown and be consistent so that there are no issues in formatting of the report given in the instruction below:
                    a. The title of the page should be like #<title>, 
                    b. heading should in the form ##<heading> 
                    c. subheading should be in the form of ###<subheading> 
                    d. finally there should not be any paragraphs and the report should only contain bullet points
                5) Always support your analysis with numbers and give the numbers in bold if possible.
    """
    return user_template

def build_html_content(html_content):
    """
    Function to build the HTML content for the report.
    Args:
        html_content (str): The HTML content to be included in the report.
    """
    # Define the HTML structure
    html_full = f"""
            <html>
            <head>
            <style>
            @page {{
            size: A4;
            margin: 15mm 15mm 15mm 15mm; /* Slightly smaller margins */
            }}
 
            body {{
            font-family: "Times New Roman", serif;
            font-size: 11pt;           /* Slightly smaller font */
            line-height: 1.2;          /* Tighter line spacing */
            margin: 0;
            padding: 0;
            color: #000;
            }}
 
            h1 {{
            font-size: 16pt;
            font-weight: bold;
            border-bottom: 1px solid #666;
            padding-bottom: 4px;
            margin: 8px 0 12px 0;
            }}
 
            h2 {{
            font-size: 13pt;
            font-weight: bold;
            border-bottom: 1px solid #bbb;
            margin: 10px 0 8px 0;
            padding-bottom: 3px;
            }}
 
            h3 {{
            font-size: 11pt;
            font-weight: bold;
            margin: 8px 0 6px 0;
            }}
 
            ul {{
            margin: 4px 0 8px 20px;   /* Reduced vertical margins */
            padding-left: 15px;
            list-style-type: disc;
            }}
 
            li {{
            margin-bottom: 3px;       /* Less space between list items */
            }}
 
            table {{
            width: 100%;
            border-collapse: collapse;
            margin: 10px 0;
            font-size: 10pt;
            margin-bottom: 16pt;
            }}
 
            th, td {{
            border: 1px solid #ccc;
            padding: 4px 6px;         /* Reduced padding */
            vertical-align: top;
            }}
 
            th {{
            background-color: #f2f2f2;
            font-weight: bold;
            }}
 
            .page-break {{
            page-break-before: always;
            }}
 
            .center-title {{
            text-align: center;
            }}
            </style>
 
            </head>
            <body>
            <h1 class="center-title">Production Issues and Deficit Recovery Plan</h1>
            {html_content}
            </body>
            </html>
    """
    return html_full
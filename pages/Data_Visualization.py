# pages/1_Visualization.py  –  full interactive EDA dashboard (all plots)
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import config

# ──────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────
st.set_page_config(page_title="Visualizations", page_icon="📊", layout="wide")
st.title("📊 Manufacturing Analytics – Visualizations")

# ──────────────────────────────────────────────
# 1. Load / cache cleaned data
# ──────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def _read_cleaned(path: str) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["Date"])

if "cleaned_df" in st.session_state:
    df = st.session_state.cleaned_df.copy()
else:
    try:
        df = _read_cleaned(config.cleaned_path)
        st.session_state.cleaned_df = df.copy()
    except Exception:
        st.error("❗ Please upload & preprocess data first on the **Data Loader** page.")
        st.stop()

# ──────────────────────────────────────────────
# 2. Build (once) & cache Plotly figures
# ──────────────────────────────────────────────
if "figs_all" not in st.session_state:

    figs_all = {
        "util_ful": {},      # {line: (fig_util, fig_ful)}
        "down_box": {},      # {line: fig_box}
        "down_bar": {},      # {line: fig_bar}
        "down_heat": {},     # {line: fig_heat}
        "issues":   {},      # {line: fig_issues}
        "prod_vs_down": {},  # {line: {shift: fig}}
        "inv_short": {},     # {line: fig_inv}
        "shifts":   sorted(df["Shift"].unique()),
    }

    # convert categorical order for nicer plots
    df["Shift"] = pd.Categorical(df["Shift"], ordered=True,
                                 categories=sorted(df["Shift"].unique()))

    # ----------------------------------------------------------
    # A. Utilization vs Shift  +  Fulfillment over Time
    # ----------------------------------------------------------
    for line in df["Production Line"].unique():
        sub = df[df["Production Line"] == line].copy()

        fig_util = px.box(
            sub, x="Shift", y="Utilization (%)",
            points="all",
            title=f"{line} • Utilization vs Shift",
            template="plotly_white"
        )

        fig_ful = px.line(
            sub.sort_values("Date"), x="Date", y="Fulfillment Rate (%)",
            markers=True,
            title=f"{line} • Fulfillment Rate over Time",
            template="plotly_white"
        )

        figs_all["util_ful"][line] = (fig_util, fig_ful)

    # ----------------------------------------------------------
    # B. Downtime distribution (box, bar, heat)
    # ----------------------------------------------------------
    for line in df["Production Line"].unique():
        sub = df[df["Production Line"] == line]

        # B1. Boxplot: Severity vs Downtime
        fig_box = px.box(
            sub, x="Issue Severity", y="Total Downtime (hrs)",
            title=f"{line} • Severity vs Downtime",
            template="plotly_white",
            points="all"
        )
        figs_all["down_box"][line] = fig_box

        # B2. Bar: downtime by Issue Type
        down_by_type = (
            sub.groupby("Issue Type")["Total Downtime (hrs)"]
               .sum().sort_values(ascending=False)
               .reset_index()
        )
        fig_bar = px.bar(
            down_by_type, x="Issue Type", y="Total Downtime (hrs)",
            title=f"{line} • Total Downtime by Issue Type",
            template="plotly_white"
        )
        figs_all["down_bar"][line] = fig_bar

        # B3. Heat-map: Shift × Issue Type
        pivot = (sub.pivot_table(index="Shift", columns="Issue Type",
                                 values="Total Downtime (hrs)",
                                 aggfunc="sum", fill_value=0)
                      .reindex(index=figs_all["shifts"]))
        fig_heat = px.imshow(
            pivot,
            labels=dict(color="Downtime (hrs)"),
            title=f"{line} • Shift vs Issue Type Downtime",
            aspect="auto",
            template="plotly_white",
            color_continuous_scale="YlOrRd"
        )
        figs_all["down_heat"][line] = fig_heat

    # ----------------------------------------------------------
    # C. Issue timelines (bubble)
    # ----------------------------------------------------------
    issues_df = df[df["Issue Severity"] != "No Issue"].copy()
    issues_df["Bubble"] = issues_df["Downtime - Issues (hrs)"] * 100

    for line in issues_df["Production Line"].unique():
        sub = issues_df[issues_df["Production Line"] == line]
        fig_iss = px.scatter(
            sub, x="Date", y="Issue Type", size="Bubble", color="Issue Type",
            title=f"{line} • Issue Timeline",
            template="plotly_white",
            size_max=30,
        )
        figs_all["issues"][line] = fig_iss

    # ----------------------------------------------------------
    # D. Production vs Downtime (per shift)
    # ----------------------------------------------------------
    df["Date"] = pd.to_datetime(df["Date"])
    agg = (df.groupby(["Date", "Production Line", "Shift"], as_index=False)
             .agg(Prod_time=("Machine Operation Time (hrs)", "sum"),
                  Downtime=("Total Downtime (hrs)", "sum")))

    for line in agg["Production Line"].unique():
        figs_all["prod_vs_down"][line] = {}
        for shift in figs_all["shifts"]:
            sub = agg[(agg["Production Line"] == line) & (agg["Shift"] == shift)]
            if sub.empty:
                continue
            fig_ts = go.Figure()
            fig_ts.add_scatter(
                x=sub["Date"], y=sub["Prod_time"],
                mode="lines+markers", name="Production Time (hrs)")
            fig_ts.add_bar(
                x=sub["Date"], y=sub["Downtime"],
                name="Total Downtime (hrs)", opacity=0.5)
            fig_ts.update_layout(
                template="plotly_white",
                title=f"{line} • {shift} – Production vs Downtime")
            figs_all["prod_vs_down"][line][shift] = fig_ts

    # ----------------------------------------------------------
    # E. Inventory, Production & Shortages
    # ----------------------------------------------------------
    for line in df["Production Line"].unique():
        sub = df[df["Production Line"] == line].sort_values("Date")
        fig_inv = go.Figure()

        fig_inv.add_scatter(
            x=sub["Date"], y=sub["Raw Material Inventory"],
            mode="lines", name="Inventory", line=dict(color="blue"))
        fig_inv.add_scatter(
            x=sub["Date"], y=sub["Downtime - Raw Material (hrs)"] * 1000,
            mode="lines", name="Downtime (hrs, scaled)",
            line=dict(color="red", dash="dash"))

        fig_inv.add_scatter(
            x=sub["Date"], y=sub["Actual Production (units)"],
            mode="lines", name="Actual Production", yaxis="y2",
            line=dict(color="green"))

        # shortages
        shortage = sub[sub["Raw Material Availability"].str.contains("Shortage", na=False)]
        fig_inv.add_scatter(
            x=shortage["Date"], y=shortage["Actual Production (units)"],
            mode="markers", name="Shortage", yaxis="y2",
            marker=dict(color="orange", symbol="x", size=10))

        fig_inv.update_layout(
            template="plotly_white",
            title=f"{line} • Inventory & Shortages",
            yaxis=dict(title="Inventory / Downtime (hrs scaled)"),
            yaxis2=dict(title="Actual Production (units)", overlaying="y", side="right")
        )
        figs_all["inv_short"][line] = fig_inv

    # ----------------------------------------------------------
    st.session_state.figs_all = figs_all

# shorthand
figs = st.session_state.figs_all
shifts = figs["shifts"]

# ──────────────────────────────────────────────
# 3. Sidebar navigation
# ──────────────────────────────────────────────
choice = st.sidebar.radio(
    "Select a chart family",
    (
        "Utilization & Fulfillment",
        "Downtime distribution",
        "Issue timelines",
        "Production vs Downtime",
        "Inventory & Shortages"
    )
)

# optional filter by production line
line_list = sorted(df["Production Line"].unique())
line_filter = st.sidebar.multiselect(
    "Filter by Production Line (blank = all)",
    options=line_list,
    default=line_list
)

# ──────────────────────────────────────────────
# 4. Render chosen family
# ──────────────────────────────────────────────
def show_line_pairs(pairs_dict):
    for line, figs_pair in pairs_dict.items():
        if line not in line_filter:
            continue
        for fig in figs_pair if isinstance(figs_pair, tuple) else figs_pair:
            st.plotly_chart(fig, use_container_width=True)

if choice == "Utilization & Fulfillment":
    for line, (fig_u, fig_f) in figs["util_ful"].items():
        if line not in line_filter:
            continue
        c1, c2 = st.columns(2)
        c1.plotly_chart(fig_u, use_container_width=True)
        c2.plotly_chart(fig_f, use_container_width=True)

elif choice == "Downtime distribution":
    for line in line_filter:
        if line not in figs["down_box"]:
            continue
        st.subheader(f"Line: {line}")
        c1, c2, c3 = st.columns(3)
        c1.plotly_chart(figs["down_box"][line], use_container_width=True)
        c2.plotly_chart(figs["down_bar"][line], use_container_width=True)
        c3.plotly_chart(figs["down_heat"][line], use_container_width=True)

elif choice == "Issue timelines":
    for line in line_filter:
        if line in figs["issues"]:
            st.plotly_chart(figs["issues"][line], use_container_width=True)

elif choice == "Production vs Downtime":
    for line in line_filter:
        if line not in figs["prod_vs_down"]:
            continue
        st.subheader(f"Line: {line}")
        cols = st.columns(len(shifts))
        for idx, shift in enumerate(shifts):
            fig = figs["prod_vs_down"][line].get(shift)
            if fig:
                cols[idx].plotly_chart(fig, use_container_width=True)
            else:
                cols[idx].empty()

else:  # Inventory & Shortages
    for line in line_filter:
        if line in figs["inv_short"]:
            st.plotly_chart(figs["inv_short"][line], use_container_width=True)

st.sidebar.success("Navigate with the sidebar – all plots stay cached! 🚀")

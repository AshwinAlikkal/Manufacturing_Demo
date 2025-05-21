import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.lines import Line2D

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import config


def load_cleaned_data():
    cleaned_df = pd.read_csv(config.cleaned_path)
    # Ensure 'Date' is datetime
    cleaned_df['Date'] = pd.to_datetime(cleaned_df['Date'])
    return cleaned_df

def plot_utilization_fulfillment_rate(df):
    lines = df['Production Line'].unique()
    n = len(lines)

    fig, axes = plt.subplots(n, 2, figsize=(15, 5 * n), sharex=False)
    if n == 1:
        axes = axes.reshape(1, -1)

    for i, line in enumerate(lines):
        sub = df[df['Production Line'] == line]

        # 1. Utilization vs Shift (Box + Strip)
        ax = axes[i, 0]
        sns.boxplot(
            x='Shift',
            y='Utilization (%)',
            data=sub,
            palette='pastel',
            ax=ax,
            showcaps=True,
            boxprops={'linewidth':1.2},
            whiskerprops={'linewidth':1.2},
            flierprops={'marker':'o','alpha':0.6}
        )
        sns.stripplot(
            x='Shift',
            y='Utilization (%)',
            data=sub,
            color='black',
            size=4,
            jitter=0.2,
            ax=ax
        )
        ax.set_title(f'{line}: Utilization vs Shift')
        ax.set_xlabel('Shift')
        ax.set_ylabel('Utilization (%)')

        # Zoom y‐axis to that line’s data range
        y_min, y_max = sub['Utilization (%)'].min(), sub['Utilization (%)'].max()
        margin = (y_max - y_min) * 0.1
        ax.set_ylim(y_min - margin, y_max + margin)

        # 2. Fulfillment Rate Over Time
        ax = axes[i, 1]
        sns.lineplot(
            x='Date',
            y='Fulfillment Rate (%)',
            data=sub,
            marker='o',
            ax=ax
        )
        ax.set_title(f'{line}: Fulfillment Rate Over Time')
        ax.set_xlabel('Date')
        ax.set_ylabel('Fulfillment Rate (%)')
        for lbl in ax.get_xticklabels():
            lbl.set_rotation(45)

    plt.tight_layout()
    fig.savefig(config.utilization_fulfillment_plot_saved_path, dpi=300)


def plot_downtime_distribution(df):
    # Identify unique production lines
    lines = df['Production Line'].unique()
    n = len(lines)

    # Create an n×3 grid of subplots
    fig, axes = plt.subplots(n, 3, figsize=(18, 6 * n), sharex=False)
    if n == 1:
        axes = axes.reshape(1, -1)  # keep 2D indexing even if only one line

    for i, line in enumerate(lines):
        sub = df[df['Production Line'] == line]

        # 1. Boxplot: Issue Severity vs Total Downtime
        sns.boxplot(
            x='Issue Severity',
            y='Total Downtime (hrs)',
            data=sub,
            palette='pastel',
            ax=axes[i, 0]
        )
        axes[i, 0].set_title(f'{line}: Severity vs Downtime')
        axes[i, 0].set_xlabel('Severity')
        axes[i, 0].set_ylabel('Downtime (hrs)')

        # 2. Bar chart: Total Downtime by Issue Type
        downtime_by_type = (
            sub.groupby('Issue Type')['Total Downtime (hrs)']
            .sum()
            .sort_values(ascending=False)
        )
        sns.barplot(
            x=downtime_by_type.index,
            y=downtime_by_type.values,
            palette='muted',
            ax=axes[i, 1]
        )
        axes[i, 1].set_title(f'{line}: Downtime by Issue Type')
        axes[i, 1].set_xlabel('Issue Type')
        axes[i, 1].set_ylabel('Total Downtime (hrs)')
        axes[i, 1].tick_params(axis='x', rotation=45)

        # 3. Heatmap: Shift vs Issue Type vs Total Downtime
        pivot = sub.pivot_table(
            index='Shift',
            columns='Issue Type',
            values='Total Downtime (hrs)',
            aggfunc='sum',
            fill_value=0
        )
        sns.heatmap(
            pivot,
            annot=True,
            fmt='.1f',
            cmap='YlOrRd',
            cbar_kws={'label': 'Downtime (hrs)'},
            ax=axes[i, 2]
        )
        axes[i, 2].set_title(f'{line}: Shift vs Issue Type Downtime')
        axes[i, 2].set_xlabel('Issue Type')
        axes[i, 2].set_ylabel('Shift')

    # Tidy and save
    plt.tight_layout()
    fig.savefig(config.downtime_distribution_plot_saved_path, dpi=300)

def plot_issues_over_time(df):
    issues = df[df['Issue Severity'] != 'No Issue'][[
    'Date', 'Production Line', 'Issue Type', 'Downtime - Issues (hrs)']].copy()

    # 2. Unique lines & issue types, plus colormap
    lines = issues['Production Line'].unique()
    issue_types = issues['Issue Type'].unique()
    cmap = plt.get_cmap('tab20')
    colors = {issue: cmap(i) for i, issue in enumerate(issue_types)}

    # 3. Create subplots
    fig, axes = plt.subplots(len(lines), 1,
                            sharex=True,
                            figsize=(14, 4 * len(lines)))

    for ax, line in zip(axes, lines):
        line_iss = issues[issues['Production Line'] == line]
        for issue in issue_types:
            sub = line_iss[line_iss['Issue Type'] == issue]
            if sub.empty:
                continue
            ax.scatter(
                sub['Date'],
                [issue] * len(sub),
                s=sub['Downtime - Issues (hrs)'] * 100,
                color=colors[issue],
                alpha=0.6
            )
        ax.set_ylabel(line, rotation=0, labelpad=40)
        ax.grid(True)

    # 4. Shared legend via proxy artists
    proxies = [
        Line2D([0], [0],
            marker='o',
            color='w',
            markerfacecolor=colors[issue],
            markersize=10,
            alpha=0.6)
        for issue in issue_types
    ]
    fig.legend(
        proxies,
        issue_types,
        title='Issue Type',
        bbox_to_anchor=(1.02, 0.5),
        loc='center left'
    )

    # 5. Final formatting and save
    axes[-1].set_xlabel('Date')
    fig.suptitle('Issue Timelines by Production Line', fontsize=16)
    fig.autofmt_xdate()
    fig.tight_layout(rect=[0, 0, 0.85, 0.96])
    plt.savefig(config.issues_timeline_plot_saved_path, dpi=300)

def production_downtime_over_time(df):
    df['Date'] = pd.to_datetime(df['Date'])                            # [10]
    relevant = ['Date','Production Line','Shift',
                'Machine Operation Time (hrs)',
                'Total Downtime (hrs)','Issue Type']
    df_filtered = df[relevant]

    # 2. Aggregate per day/line/shift
    agg = (df_filtered
        .groupby(['Date','Production Line','Shift'], dropna=False)
        .agg({'Machine Operation Time (hrs)': 'sum',
                'Total Downtime (hrs)': 'sum',
                'Issue Type': lambda x: ', '.join(sorted(set(i for i in x if pd.notna(i))))})
        .reset_index())                                              # [11]

    # 3. Setup subplot grid
    lines = agg['Production Line'].unique()
    shifts = agg['Shift'].unique()
    fig, axes = plt.subplots(len(lines), len(shifts),
                            sharex=True, figsize=(16, 4*len(lines)))

    # Ensure axes is 2D
    if axes.ndim == 1:
        axes = axes.reshape(len(lines), -1)

    # 4. Plot each cell
    for i, line in enumerate(lines):
        for j, shift in enumerate(shifts):
            ax = axes[i][j]
            sub = agg[(agg['Production Line']==line) & (agg['Shift']==shift)]
            # Production trend
            ax.plot(sub['Date'], sub['Machine Operation Time (hrs)'],
                    color='tab:blue', label='Production Time (hrs)')
            # Downtime bars
            ax.bar(sub['Date'], sub['Total Downtime (hrs)'],
                color='tab:red', alpha=0.5, label='Total Downtime (hrs)')
            # Annotate issues
            for _, row in sub.iterrows():
                if row['Issue Type']:
                    ax.text(row['Date'], row['Total Downtime (hrs)']+0.1,
                            row['Issue Type'], rotation=90,
                            fontsize=6, va='bottom')
            ax.set_title(f'{line} – {shift}')
            ax.set_ylabel('Hours')
            ax.grid(True)
            if i==0 and j==0:
                ax.legend(loc='upper left')

    # 5. Final layout & save
    axes[-1][-1].set_xlabel('Date')
    fig.suptitle('Production Trend, Downtime & Issue Types by Line & Shift', fontsize=16)
    fig.autofmt_xdate()
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(config.production_downtime_saved_path, dpi = 300)

def plot_with_shortage_markers_combined(df):
    df['Date'] = pd.to_datetime(df['Date'])
    lines = df['Production Line'].unique()
    num_lines = len(lines)

    fig, axes = plt.subplots(num_lines, 1, figsize=(12, 6*num_lines), constrained_layout=True)

    if num_lines == 1:
        axes = [axes]

    for ax, line in zip(axes, lines):
        line_df = df[df['Production Line'] == line].sort_values('Date')
        ax.plot(line_df['Date'], line_df['Raw Material Inventory'], color='blue', label='Inventory')
        ax.plot(line_df['Date'], line_df['Downtime - Raw Material (hrs)']*1000, '--', color='red', label='Downtime (hrs, scaled)')
        ax2 = ax.twinx()
        ax2.plot(line_df['Date'], line_df['Actual Production (units)'], color='green', label='Actual Production')

        # Highlight shortages
        shortage_df = line_df[line_df['Raw Material Availability'].str.contains('Shortage')]
        ax2.scatter(shortage_df['Date'], shortage_df['Actual Production (units)'],
                    color='orange', marker='x', s=100, label='Shortage')

        # Combine legends
        lines_1, labels_1 = ax.get_legend_handles_labels()
        lines_2, labels_2 = ax2.get_legend_handles_labels()
        ax.legend(lines_1 + lines_2, labels_1 + labels_2, loc='upper left')
        ax.set_title(f'{line} - Combined Production & Raw Material Trends (Shortages Highlighted)')
        ax.tick_params(axis='x', rotation=45)

    plt.savefig(config.combined_production_rm_saved_path, dpi=85, bbox_inches='tight')



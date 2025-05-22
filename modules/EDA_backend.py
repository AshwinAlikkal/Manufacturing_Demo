import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import matplotlib.dates as mdates
from datetime import timedelta
from modules import gcs
import config
from matplotlib.gridspec import GridSpec

def create_combined_linewise_figure(df, line, save_path, date, shift):
    def force_tick_with_april_30(ax, dates, n_ticks=6):
        april_30 = pd.to_datetime("2025-04-30")
        dates = pd.to_datetime(dates)
        min_date, max_date = dates.min(), dates.max()
        if april_30 > max_date:
            max_date = april_30
        ticks = pd.date_range(min_date, max_date, periods=n_ticks - 1).tolist()
        if april_30 not in ticks:
            ticks.append(april_30)
        ticks = sorted(set(ticks))
        ax.set_xticks(mdates.date2num(ticks))
        ax.set_xticklabels([d.strftime('%Y-%m-%d') for d in ticks], rotation=90, ha='center')

    cutoff_date = pd.to_datetime(date)
    df = df.copy()
    df['Date'] = pd.to_datetime(df['Date'])
    line_df = df[df['Production Line'] == line]

    # Filtering: only selected shift on cutoff, all shifts after
    selected_shift = shift
    filtered_cutoff_shift = line_df[(line_df['Date'] == cutoff_date) & (line_df['Shift'] == selected_shift)]
    filtered_after_cutoff = line_df[line_df['Date'] > cutoff_date]
    filtered_df = pd.concat([filtered_cutoff_shift, filtered_after_cutoff]).sort_values(['Date', 'Shift']).reset_index(drop=True)

    fig = plt.figure(figsize=(16, 12), constrained_layout=True)
    gs = GridSpec(3, 2, figure=fig, height_ratios=[1, 1.3, 1.6])

    # --- Box Plot (Filtered Data) ---
    ax1 = fig.add_subplot(gs[0, :])
    box_df = filtered_df[(filtered_df['Date'] >= cutoff_date)]
    sns.boxplot(x='Issue Severity', y='Total Downtime (hrs)', data=box_df, palette='pastel', ax=ax1)
    ax1.set_title(f'{line} – Severity vs Downtime ({selected_shift} Shift)', fontsize=12)
    ax1.set_ylabel('Total Downtime (hrs)')

    # --- Inventory & Production Over Time (Full Data) ---
    ax2 = fig.add_subplot(gs[1, 0])
    ax2_2 = ax2.twinx()
    sorted_df = line_df.sort_values('Date')

    ax2.plot(sorted_df['Date'], sorted_df['Raw Material Inventory'], label='Inventory', color='tab:blue')
    ax2.plot(sorted_df['Date'], sorted_df['Downtime - Raw Material (hrs)'] * 1000, '--', label='Downtime (×1000)', color='tab:red')
    ax2_2.plot(sorted_df['Date'], sorted_df['Actual Production (units)'], label='Production', color='tab:green')

    shortage = sorted_df[sorted_df['Raw Material Availability'].str.contains('Shortage', na=False)]
    ax2_2.scatter(shortage['Date'], shortage['Actual Production (units)'], color='orange', marker='x', s=80, label='Shortage')

    max_date = sorted_df['Date'].max()
    extended_max_date = max_date + timedelta(days=1)
    ax2.set_xlim(sorted_df['Date'].min(), extended_max_date)
    ax2_2.set_xlim(sorted_df['Date'].min(), extended_max_date)

    right_limit_num = ax2.get_xlim()[1]
    right_limit = mdates.num2date(right_limit_num)
    ax2.axvspan(cutoff_date, right_limit, color='#FFD700', alpha=0.2)
    ax2_2.axvspan(cutoff_date, right_limit, color='#FFD700', alpha=0.2)

    force_tick_with_april_30(ax2, sorted_df['Date'])
    force_tick_with_april_30(ax2_2, sorted_df['Date'])

    ax2.set_title(f'{line} – Inventory & Production Over Time', fontsize=11)
    ax2.set_ylabel('Inventory / Downtime')
    ax2_2.set_ylabel('Production (units)')
    h1, l1 = ax2.get_legend_handles_labels()
    h2, l2 = ax2_2.get_legend_handles_labels()
    ax2.legend(h1 + h2, l1 + l2, loc='upper left', fontsize=9)

    # --- Heatmap (Filtered Data) ---
    ax_heat = fig.add_subplot(gs[1, 1])
    heat_df = filtered_df[filtered_df['Date'] >= cutoff_date]
    pivot = heat_df.pivot_table(index='Shift', columns='Issue Type', values='Total Downtime (hrs)', aggfunc='sum', fill_value=0)

    if pivot.empty or pivot.values.sum() == 0:
        dummy = pd.DataFrame([[0]], index=[f'{selected_shift} Shift'], columns=['No Issues'])
        sns.heatmap(dummy, annot=[['no issues']], fmt='', cmap='YlOrRd', cbar=False, ax=ax_heat)
        ax_heat.set_title(f'{line} – {selected_shift} Shift: No Issues Reported', fontsize=11)
    else:
        sns.heatmap(pivot, annot=True, fmt='.1f', cmap='YlOrRd', cbar_kws={'label': 'Downtime (hrs)'}, ax=ax_heat)
        ax_heat.set_title(f'{line} – {selected_shift} Shift Issue Downtime', fontsize=11)

    # --- Per-Shift Trend Plots (Full Data) ---
    shifts = line_df['Shift'].dropna().unique()
    for j, shift in enumerate(shifts):
        ax3 = fig.add_subplot(gs[2, j])
        sub = line_df[line_df['Shift'] == shift].copy()
        sub_agg = sub.groupby('Date', as_index=False).agg({
            'Machine Operation Time (hrs)': 'sum',
            'Total Downtime (hrs)': 'sum',
            'Issue Type': lambda x: ', '.join(sorted(set(i for i in x if pd.notna(i))))
        })

        ax3.plot(sub_agg['Date'], sub_agg['Machine Operation Time (hrs)'], color='tab:blue', label='Prod Time (hrs)')
        bar_width = pd.Timedelta(days=0.8)
        bars = ax3.bar(sub_agg['Date'], sub_agg['Total Downtime (hrs)'], width=bar_width, color='tab:red', alpha=0.5, label='Downtime (hrs)')

        try:
            labels = [txt if txt else 'no issues' for txt in sub_agg['Issue Type']]
            ax3.bar_label(bars, labels=labels, rotation=90, label_type='edge', fontsize=12, padding=3)
        except AttributeError:
            for bar, txt in zip(bars, sub_agg['Issue Type']):
                ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1, txt or 'no issues',
                         ha='center', va='bottom', rotation=90, fontsize=12)

        x_right_date = sub['Date'].max() + timedelta(days=2) if not sub.empty else cutoff_date + timedelta(days=2)
        ax3.set_xlim(sub['Date'].min(), x_right_date)

        if x_right_date > cutoff_date:
            ax3.axvspan(cutoff_date, x_right_date, color='#FFD700', alpha=0.5)

        force_tick_with_april_30(ax3, sub_agg['Date'])
        ax3.set_title(f'{line} – {shift} Shift')
        ax3.set_ylabel('Hours')
        ax3.grid(True)
        if j == 0:
            ax3.legend(loc='upper left')

    gcs.smart_savefig(fig, save_path, config.local_eda_flag, dpi=300, bbox_inches='tight')
    plt.close(fig)
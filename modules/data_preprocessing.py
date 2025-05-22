# modules/data_preprocessing.py

import pandas as pd
import os
import config
from modules import gcs  # ✅ added

# Financial assumptions
FINANCIAL_PARAMS = {
    'unit_price': 150,
    'unit_cost': 100,
    'gross_profit_per_unit': 50,
    'downtime_cost_per_hr': 5000,
    'holding_cost_rate': 0.2
}

def load_data():
    issues = pd.read_excel(config.issues_filepath)
    production = pd.read_excel(config.production_filepath)
    demand = pd.read_excel(config.demand_filepath)
    return issues, production, demand

def merge_data(issues, production, demand):
    merged = pd.merge(issues, production, on=['Date', 'Production Line', 'Shift'], how='inner')
    merged = pd.merge(merged, demand, on=['Date', 'Production Line', 'Shift'], how='inner')
    return merged

def load_and_preprocess(filepath):
    df = gcs.load_dataframe(filepath, config.local_data_flag)  # ✅ uses GCS if needed

    # Actual Production
    if 'Production Rate (units/hr)' in df.columns:
        df['Actual Production (units)'] = df['Production Rate (units/hr)'] * (
            df['Machine Operation Time (hrs)'] - df['Total Downtime (hrs)'])

    # Production Deficit
    df['Production_Deficit'] = df['Consumer Demand'] - df['Actual Production (units)']

    # Utilization (%)
    if 'Utilization (%)' not in df.columns:
        df['Utilization (%)'] = (
            (df['Machine Operation Time (hrs)'] - df['Total Downtime (hrs)']) / df['Machine Operation Time (hrs)']
        ).clip(upper=1).fillna(0) * 100

    # Fulfillment Rate (%)
    if 'Fulfillment Rate (%)' not in df.columns:
        df['Fulfillment Rate (%)'] = (
            df['Actual Production (units)'] / df['Consumer Demand']
        ).clip(upper=1).fillna(0) * 100

    return df

def generate_unit_metrics(cleaned_df):
    units = cleaned_df['Production Line'].unique()
    metrics = {}

    for unit in units:
        unit_df = cleaned_df[cleaned_df['Production Line'] == unit]
        metrics[unit] = {
            'production': {
                'total': unit_df['Actual Production (units)'].sum(),
                'avg_daily': unit_df['Actual Production (units)'].mean(),
                'max_daily': unit_df['Actual Production (units)'].max(),
                'min_daily': unit_df['Actual Production (units)'].min(),
                'std_daily': unit_df['Actual Production (units)'].std()
            },
            'downtime': {
                'total_hrs': unit_df['Total Downtime (hrs)'].sum(),
                'avg_daily': unit_df['Total Downtime (hrs)'].mean(),
                'breakdown': {
                    'raw_material': unit_df['Downtime - Raw Material (hrs)'].mean(),
                    'issues': unit_df['Downtime - Issues (hrs)'].mean()
                }
            },
            'inventory': {
                'avg_daily': unit_df['Raw Material Inventory'].mean(),
                'min_daily': unit_df['Raw Material Inventory'].min(),
                'shortage_days': unit_df[unit_df['Raw Material Availability'].str.contains('Shortage')].shape[0]
            },
            'efficiency': {
                'avg_utilization': unit_df['Utilization (%)'].mean(),
                'avg_fulfillment': unit_df['Fulfillment Rate (%)'].mean()
            }
        }

        metrics[unit]['financials'] = {
            'total_revenue': metrics[unit]['production']['total'] * FINANCIAL_PARAMS['unit_price'],
            'total_cost': metrics[unit]['production']['total'] * FINANCIAL_PARAMS['unit_cost'],
            'gross_profit': metrics[unit]['production']['total'] * FINANCIAL_PARAMS['gross_profit_per_unit'],
            'downtime_cost': metrics[unit]['downtime']['total_hrs'] * FINANCIAL_PARAMS['downtime_cost_per_hr'],
            'net_profit': (
                metrics[unit]['production']['total'] * FINANCIAL_PARAMS['gross_profit_per_unit']
                - metrics[unit]['downtime']['total_hrs'] * FINANCIAL_PARAMS['downtime_cost_per_hr']
            ),
            'profit_margin': 0  # to be calculated next
        }

        if metrics[unit]['financials']['total_revenue'] > 0:
            metrics[unit]['financials']['profit_margin'] = (
                metrics[unit]['financials']['net_profit'] /
                metrics[unit]['financials']['total_revenue']
            ) * 100

    return metrics

def flatten_dict(d, parent_key='', sep='_'):
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

def metrics_to_matrix(metrics):
    flat_metrics = {}
    for unit, unit_metrics in metrics.items():
        flat_metrics[unit] = flatten_dict(unit_metrics)
    df_matrix = pd.DataFrame.from_dict(flat_metrics, orient='index')
    df_matrix.index.name = 'Production Line'
    return df_matrix.reset_index()

def preprocess_and_save():
    issues, production, demand = load_data()
    merged = merge_data(issues, production, demand)
    gcs.save_dataframe(merged, config.merged_data_filepath, config.local_data_flag) 

    cleaned_df = load_and_preprocess(config.merged_data_filepath)
    gcs.save_dataframe(cleaned_df, config.cleaned_path, config.local_data_flag)  
    metrics = generate_unit_metrics(cleaned_df)
    df_matrix = metrics_to_matrix(metrics)
    gcs.save_dataframe(df_matrix, config.linewise_pivot_data_filepath, config.local_data_flag)  

# ✅ DO NOT CALL ANYTHING HERE OUTSIDE MAIN
if __name__ == "__main__":
    preprocess_and_save()
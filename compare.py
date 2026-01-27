import re
import os
import pandas as pd
import argparse
import webbrowser
from pathlib import Path

def parse_arguments():
    parser = argparse.ArgumentParser(description='Compare strategy variations from Short_Analysis.html')
    parser.add_argument('output_dir', type=str, help='Path to the output folder containing Short_Analysis.html')
    return parser.parse_args()

def extract_metrics(html_content):
    # Regular expression to find report headers and their metrics
    report_pattern = re.compile(r"<h3>\d+\. Report: <a[^>]*>(.*?)</a></h3>.*?<ul class='metrics-list'>(.*?)</ul>", re.DOTALL)
    
    # Regular expression to extract metrics from the list
    metric_pattern = re.compile(r"<li><strong>(.*?)</strong>: (.*?)</li>")
    
    results = []
    
    for report_name, metrics_html in report_pattern.findall(html_content):
        # Improved suffix detection
        # Matches patterns like _ld1, _t18, _v1, etc.
        match = re.search(r'(.*?)_([a-zA-Z]+\d+)$', report_name)
        if match:
            base_name = match.group(1)
            variant = match.group(2)
        else:
            base_name = report_name
            variant = "Original"
        
        metrics = {}
        target_metrics = ["Total PnL", "Max Drawdown", "Recovery Factor", "Max Trades in Sequence", "Buy Trades", "Sell Trades"]
        
        for metric_name, metric_value in metric_pattern.findall(metrics_html):
            if metric_name in target_metrics:
                # Clean drawdown values
                if metric_name == "Max Drawdown":
                    val_match = re.search(r'([-\d\.,]+)', metric_value)
                    metrics[metric_name] = val_match.group(1) if val_match else metric_value
                elif metric_name == "Max Trades in Sequence":
                    val_match = re.search(r'(\d+)', metric_value)
                    metrics[metric_name] = val_match.group(1) if val_match else metric_value
                else:
                    metrics[metric_name] = metric_value
        
        results.append({
            'Base': base_name,
            'Variant': variant,
            **metrics
        })
    return results

def generate_report(results, output_file):
    df = pd.DataFrame(results)
    
    # Identify strategies with variants
    base_counts = df['Base'].value_counts()
    strategies_with_variants = base_counts[base_counts > 1].index.tolist()
    
    if not strategies_with_variants:
        print("No strategy variants detected.")
        return False
    
    # Filter to only include strategies with variants
    df = df[df['Base'].isin(strategies_with_variants)]
    
    output_rows = []
    all_variants = sorted(list(df['Variant'].unique()))
    
    # Ensure "Original" is first if present
    if "Original" in all_variants:
        all_variants.remove("Original")
        all_variants = ["Original"] + all_variants
    
    for base, group in df.groupby('Base'):
        row = {'Base Strategy': base}
        for _, item in group.iterrows():
            var = item['Variant']
            metrics_str = f"PnL: {item.get('Total PnL', 'N/A')}<br>" \
                          f"DD: {item.get('Max Drawdown', 'N/A')}<br>" \
                          f"RF: {item.get('Recovery Factor', 'N/A')}<br>" \
                          f"MaxT: {item.get('Max Trades in Sequence', 'N/A')}<br>" \
                          f"B/S: {item.get('Buy Trades', 'N/A')}/{item.get('Sell Trades', 'N/A')}"
            row[var] = metrics_str
        output_rows.append(row)
    
    final_df = pd.DataFrame(output_rows)
    
    # Reorder columns: Base Strategy first, then other variants in order
    cols = ['Base Strategy'] + [v for v in all_variants if v in final_df.columns]
    final_df = final_df[cols]
    
    html_output = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Strategy Comparison Report</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; color: #333; margin: 20px; }}
        h2 {{ color: #2c3e50; text-align: center; margin-bottom: 30px; }}
        table {{ border-collapse: collapse; width: 100%; box-shadow: 0 4px 6px rgba(0,0,0,0.1); background-color: white; border-radius: 8px; overflow: hidden; }}
        th, td {{ border: 1px solid #eee; padding: 15px; text-align: left; vertical-align: top; }}
        th {{ background-color: #3498db; color: white; font-weight: 600; text-transform: uppercase; font-size: 0.9em; letter-spacing: 1px; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
        tr:hover {{ background-color: #f1f1f1; }}
        .base-name {{ font-weight: bold; color: #2980b9; }}
        .metric-block {{ line-height: 1.6; font-size: 0.9em; }}
    </style>
</head>
<body>
    <h2>Strategy Variant Comparison</h2>
    {final_df.to_html(index=False, escape=False, classes='comparison-table')}
</body>
</html>
"""
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_output)
    print(f"Report saved to: {output_file}")
    return True

def main():
    args = parse_arguments()
    
    output_dir = os.path.abspath(args.output_dir)
    html_file = os.path.join(output_dir, 'Short_Analysis.html')

    if not os.path.exists(html_file):
        print(f"Error: {html_file} not found.")
        return

    print(f"Reading: {html_file}")
    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()

    results = extract_metrics(html_content)
    if not results:
        print("No metrics found in the report.")
        return

    output_file = os.path.join(output_dir, 'compare_report.html')
    if generate_report(results, output_file):
        webbrowser.open(f"file:///{output_file}")

if __name__ == "__main__":
    main()

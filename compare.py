import re
import os
import pandas as pd
import argparse
import webbrowser
from pathlib import Path
from bs4 import BeautifulSoup

def parse_arguments():
    parser = argparse.ArgumentParser(description='Compare strategy variations from Short_Analysis.html')
    parser.add_argument('output_dir', type=str, help='Path to the output folder containing Short_Analysis.html')
    return parser.parse_args()

def extract_metrics(html_content):
    # Regular expression to find report headers and their metrics
    # Made <a> tag optional and more robust to whitespace
    report_pattern = re.compile(r"<h3>\d+\. Report: (?:<a[^>]*>)?(.*?)(?:</a>)?</h3>.*?<ul class='metrics-list'>(.*?)</ul>", re.DOTALL)
    
    # Regular expression to extract metrics from the list
    metric_pattern = re.compile(r"<li><strong>(.*?)</strong>: (.*?)</li>")
    
    results = []
    
    for report_name, metrics_html in report_pattern.findall(html_content):
        report_name = report_name.strip()
        # Improved suffix detection
        # 1. Strip common extensions that might be duplicated or nested
        clean_name = re.sub(r'(\.set|\.html?)+$', '', report_name, flags=re.IGNORECASE).strip()
        
        # 2. Matches patterns like _ld1, _v1, etc.
        match = re.search(r'^(.*?)_([a-zA-Z]+\d+)$', clean_name)
        if match:
            base_name = match.group(1).strip()
            variant = match.group(2).strip()
        else:
            base_name = clean_name
            variant = "Original"
        
        # print(f"DEBUG: Found report '{report_name}' -> Base: '{base_name}', Variant: '{variant}'")
        
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
            'FullReportName': report_name,
            **metrics
        })
    return results

def get_selected_reports(output_dir):
    """Parse Full_Analysis.html to find which reports are in the Monthly Contributor Breakdown."""
    full_analysis_path = os.path.join(output_dir, "Full_Analysis.html")
    if not os.path.exists(full_analysis_path):
        return set()

    try:
        with open(full_analysis_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')
        
        # Look for the Monthly Contributor Breakdown header
        header = soup.find(['h2', 'h3'], string=lambda t: t and 'Monthly Contributor Breakdown' in t)
        if not header:
            header = soup.find(lambda tag: tag.name in ['h2', 'h3'] and 'Monthly Contributor Breakdown' in tag.get_text())
        
        if not header:
            return set()

        table = header.find_next('table')
        if not table:
            return set()

        selected = set()
        rows = table.find_all('tr')[1:] # Skip header row
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 3: continue
            
            # The filename is in the 3rd column (index 2)
            report_file_td = cols[2]
            code_tag = report_file_td.find('code')
            if code_tag:
                name = code_tag.get_text(strip=True)
                # Remove .htm, .html, or .set extension for matching
                base_name = re.sub(r'(\.set|\.html?)+$', '', name, flags=re.IGNORECASE)
                selected.add(base_name)
        return selected
    except Exception as e:
        print(f"Warning: Could not parse Full_Analysis.html for selected reports: {e}")
        return set()

def generate_report(results, output_file, selected_reports=None):
    if selected_reports is None:
        selected_reports = set()
    
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
            full_name = item.get('FullReportName', '')
            
            # Check if this variation is "selected"
            # Normalize full_name for comparison
            normalized_full_name = re.sub(r'(\.set|\.html?)+$', '', full_name, flags=re.IGNORECASE)
            is_selected = normalized_full_name in selected_reports
            marker = " <span class='selected-marker'>*</span>" if is_selected else ""
            bold_style = " style='font-weight: bold;'" if is_selected else ""
            
            metrics_str = f"<div class='metric-block'{bold_style}>" \
                          f"PnL: {item.get('Total PnL', 'N/A')}{marker}<br>" \
                          f"DD: {item.get('Max Drawdown', 'N/A')}<br>" \
                          f"RF: {item.get('Recovery Factor', 'N/A')}<br>" \
                          f"MaxT: {item.get('Max Trades in Sequence', 'N/A')}<br>" \
                          f"B/S: {item.get('Buy Trades', 'N/A')}/{item.get('Sell Trades', 'N/A')}" \
                          f"</div>"
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
        .selected-marker {{ color: #e74c3c; font-weight: bold; font-size: 1.2em; }}
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
    # Switch to Full_Analysis.html to ensure we see all variants including skipped ones
    html_file = os.path.join(output_dir, 'Full_Analysis.html')
    if not os.path.exists(html_file):
        # Fallback to Short_Analysis.html if Full doesn't exist
        html_file = os.path.join(output_dir, 'Short_Analysis.html')
        print(f"Error: {html_file} not found.")
        return

    print(f"Reading: {html_file}")
    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()

    results = extract_metrics(html_content)
    if not results:
        print("No metrics found in the report.")
        return

    selected_reports = get_selected_reports(output_dir)
    if selected_reports:
        print(f"Found {len(selected_reports)} selected variations in Full_Analysis.html")

    output_file = os.path.join(output_dir, 'compare_report.html')
    if generate_report(results, output_file, selected_reports):
        webbrowser.open(f"file:///{output_file}")

if __name__ == "__main__":
    main()

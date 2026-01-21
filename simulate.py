import os
import argparse
import re
from bs4 import BeautifulSoup
import pandas as pd
import webbrowser

def parse_full_analysis(html_path):
    if not os.path.exists(html_path):
        print(f"Error: {html_path} not found.")
        return None

    with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    soup = BeautifulSoup(content, 'html.parser')
    
    # 1. Extract data from Monthly Contributor Breakdown table
    contributor_data = []
    h2_contributor = soup.find(['h2', 'h3'], string=lambda t: t and 'Monthly Contributor Breakdown' in t)
    if not h2_contributor:
        h2_contributor = soup.find(lambda tag: tag.name in ['h2', 'h3'] and 'Monthly Contributor Breakdown' in tag.get_text())
    
    if h2_contributor:
        table = h2_contributor.find_next('table')
        if table:
            rows = table.find_all('tr')[1:] # Skip header
            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 4: continue
                
                if "Total" in cols[0].get_text() or "Total" in cols[1].get_text():
                    continue
                
                symbol = cols[1].get_text(strip=True)
                report_file_td = cols[2]
                a_tag = report_file_td.find('a')
                report_file = a_tag.get_text(strip=True) if a_tag else report_file_td.get_text(strip=True)
                
                total_profit_text = cols[-1].get_text(strip=True)
                try:
                    total_profit = float(total_profit_text.replace(',', ''))
                except:
                    total_profit = 0.0
                
                contributor_data.append({
                    'Symbol': symbol,
                    'ReportFile': report_file,
                    'TotalProfit': total_profit
                })

    # 2. Extract detailed metrics and parameters for each report section
    report_details = {}
    detailed_sections = soup.find_all('h3')

    def find_li_by_text(ul, search_text):
        if not ul: return None
        for li in ul.find_all('li'):
            if search_text in li.get_text():
                return li
        return None

    for h3 in detailed_sections:
        h3_text = h3.get_text()
        if 'Report:' not in h3_text: continue
        # Extract report name (allowing for SN. Report: Name format or similar)
        report_name = h3_text.split('Report:')[-1].strip()
        
        details = {
            'InitialLot': 0.01,
            'MaxDD': 0.0,
            'SelectedPnL': 0.0,
            'TotalPnL': 0.0,
            'MaxTrades': "N/A",
            'MaxTradesGap': "N/A",
            'BasePipStep': "N/A",
            'ReportLink': "",
            'Sim1kData': {}
        }
        
        # Extract report link if available
        a_tag = h3.find('a')
        if a_tag and a_tag.has_attr('href'):
            details['ReportLink'] = a_tag['href']
        
        # --- Metrics extraction ---
        metrics_list = h3.find_next('ul', class_='metrics-list')
        if metrics_list:
            lis = metrics_list.find_all('li')
            for li in lis:
                li_text = li.get_text(separator=" ").strip()
                if 'Max Drawdown' in li_text:
                    match = re.search(r'Max Drawdown[:\s]+(-?[\d,.]+)', li_text)
                    if match:
                        try: details['MaxDD'] = float(match.group(1).replace(',', ''))
                        except: pass
                elif 'Total PnL' in li_text:
                    match = re.search(r'Total PnL[:\s]+(-?[\d,.]+)', li_text)
                    if match:
                        try: details['TotalPnL'] = float(match.group(1).replace(',', ''))
                        except: pass
                elif 'Selected PnL' in li_text:
                    match = re.search(r'Selected PnL[:\s]+(-?[\d,.]+)', li_text)
                    if match:
                        try: details['SelectedPnL'] = float(match.group(1).replace(',', ''))
                        except: pass
                elif 'Max Trades in Sequence' in li_text:
                    # Look for "Value [Date]"
                    match = re.search(r'Max Trades in Sequence[:\s]+(\d+)\s*\[([^\]]+)\]', li_text)
                    if match:
                        details['MaxTrades'] = f"{match.group(1)} <br><small>({match.group(2)})</small>"
                    else:
                        try: details['MaxTrades'] = li_text.split(':')[-1].strip()
                        except: pass
                elif 'Pip Gap at Max Trades' in li_text:
                    try: details['MaxTradesGap'] = li_text.split(':')[-1].strip()
                    except: pass

        # --- Parameters extraction ---
        params_list = h3.find_next('ul', class_='params-list')
        if params_list:
            li_lot = find_li_by_text(params_list, 'Initial LotSize')
            if li_lot:
                code = li_lot.find('code')
                try: details['InitialLot'] = float(code.get_text(strip=True)) if code else float(li_lot.get_text().split(':')[-1].strip())
                except: pass
            
            li_pip = find_li_by_text(params_list, 'Pip Step')
            if li_pip:
                code = li_pip.find('code')
                details['BasePipStep'] = code.get_text(strip=True) if code else li_pip.get_text().split(':')[-1].strip()

        # --- 1k Threshold Table extraction ---
        current_node = h3.find_next()
        while current_node and not (current_node.name == 'h3' or current_node.name == 'h2'):
            node_text = current_node.get_text()
            
            # --- Extract Base Pip Gap from Theoretical Max DD Summary ---
            if 'Theoretical Max DD Summary' in node_text:
                theo_table = current_node.find_next('table')
                if not theo_table and current_node.name == 'li':
                     theo_table = current_node.find('table') # Try inside the LI

                if theo_table:
                    # Look for scenario label header (th with colspan)
                    th_labels = theo_table.find_all('th')
                    for th in th_labels:
                        th_text = th.get_text()
                        if 'Base Pip Gap' in th_text:
                            match = re.search(r'Base Pip Gap[:\s]+([\d.]+)', th_text)
                            if match:
                                details['MaxTradesGap'] = match.group(1).strip()
                                break # Take the first scenario (usually the highest gap)

            # --- 1k Threshold Table extraction ---
            if '1k Drawdown Threshold vs. Starting Lot' in node_text:
                thresh_table = current_node.find_next('table')
                if not thresh_table and current_node.name == 'li':
                    thresh_table = current_node.find('table')

                if thresh_table:
                    headers = [th.get_text(strip=True) for th in thresh_table.find_all('th')]
                    rows = thresh_table.find_all('tr')[1:]
                    
                    gap_row = []
                    level_row = []
                    for row in rows:
                        cells = [td.get_text(strip=True) for td in row.find_all('td')]
                        if not cells: continue
                        if '1k Pip Gap' in cells[0]:
                            gap_row = cells[1:]
                        elif 'Trade Level' in cells[0]:
                            level_row = cells[1:]
                    
                    lots_in_table = headers[1:]
                    for idx, lot_str in enumerate(lots_in_table):
                        try:
                            lot_val = float(lot_str.replace(',', ''))
                            details['Sim1kData'][lot_val] = {
                                'gap': gap_row[idx] if idx < len(gap_row) else "N/A",
                                'level': level_row[idx] if idx < len(level_row) else "N/A"
                            }
                        except: pass
            current_node = current_node.find_next()

        report_details[report_name] = details

    # 3. Handle contributor_data and merge
    if not contributor_data:
        print("Note: Monthly Contributor Breakdown table not found. Using Detailed Per-Report sections.")
        for rname, det in report_details.items():
            pnl_to_use = det['SelectedPnL'] if det['SelectedPnL'] != 0 else det['TotalPnL']
            contributor_data.append({
                'Symbol': rname.split('_')[2] if '_' in rname and len(rname.split('_')) > 2 else "Unknown",
                'ReportFile': rname + ".htm",
                'TotalProfit': pnl_to_use
            })

    # Final Merge
    final_data = []
    for item in contributor_data:
        basename = os.path.splitext(item['ReportFile'])[0]
        # Match by trying exact match or partial match
        details = None
        if basename in report_details:
            details = report_details[basename]
        else:
            # Try to find which key in report_details contains the basename
            for k in report_details.keys():
                if basename in k or k in basename:
                    details = report_details[k]
                    break
        
        if details:
            item.update(details)
        else:
            # Fallback defaults
            item.update({
                'InitialLot': 0.01,
                'MaxDD': 0.0,
                'MaxTrades': "N/A",
                'MaxTradesGap': "N/A",
                'BasePipStep': "N/A",
                'ReportLink': "",
                'Sim1kData': {}
            })
        final_data.append(item)

    return final_data

def generate_sim_html(data, output_path):
    sim_lots = [0.01, 0.02, 0.03, 0.04, 0.05]
    
    html = """<!DOCTYPE html>
<html lang='en'>
<head>
    <meta charset='UTF-8'>
    <meta name='viewport' content='width=device-width, initial-scale=1.0'>
    <title>Simulation Report</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; max-width: 1600px; margin: 0 auto; padding: 20px; background-color: #f4f7f6; }
        h1, h2 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; margin-top: 30px; }
        table { border-collapse: collapse; width: 100%; margin: 20px 0; background-color: #fff; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        th, td { padding: 8px 10px; border: 1px solid #ddd; text-align: left; font-size: 0.85em; }
        th { background-color: #3498db; color: white; white-space: nowrap; }
        tr:nth-child(even) { background-color: #f9f9f9; }
        .sim-header { background-color: #2980b9; text-align: center; }
        .sub-header { background-color: #ecf0f1; color: #333; font-weight: bold; text-align: center; font-size: 0.8em; }
        .profit { color: #27ae60; font-weight: bold; }
        .drawdown { color: #e74c3c; }
        .summary-box { background-color: #fff; padding: 15px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .threshold { color: #8e44ad; font-style: italic; }
    </style>
</head>
<body>
<h1>Simulation Report (Varying Lot Sizes)</h1>
<div class='summary-box'>
    <p>This report simulates performance and $1,000 drawdown thresholds for fixed lot sizes.</p>
    <p>PnL and MaxDD are scaled linearly: <code>Multiplier = Target Lot / Initial Lot</code>.</p>
    <p>1k Pip Gap and Trade Level are extracted directly from the original report's sensitivity analysis.</p>
</div>

<table>
<thead>
    <tr>
        <th rowspan="2">S.No</th>
        <th rowspan="2">Symbol</th>
        <th rowspan="2">Report File</th>
        <th rowspan="2">Max Trades<br>(Seq)</th>
        <th rowspan="2">Pip Gap<br>(Max Seq)</th>
        <th colspan="4" class="sim-header">Lot 0.01</th>
        <th colspan="4" class="sim-header">Lot 0.02</th>
        <th colspan="4" class="sim-header">Lot 0.03</th>
        <th colspan="4" class="sim-header">Lot 0.04</th>
        <th colspan="4" class="sim-header">Lot 0.05</th>
    </tr>
    <tr>
        <th class="sub-header">PnL</th><th class="sub-header">MaxDD</th><th class="sub-header">1k Gap</th><th class="sub-header">1k Lvl</th>
        <th class="sub-header">PnL</th><th class="sub-header">MaxDD</th><th class="sub-header">1k Gap</th><th class="sub-header">1k Lvl</th>
        <th class="sub-header">PnL</th><th class="sub-header">MaxDD</th><th class="sub-header">1k Gap</th><th class="sub-header">1k Lvl</th>
        <th class="sub-header">PnL</th><th class="sub-header">MaxDD</th><th class="sub-header">1k Gap</th><th class="sub-header">1k Lvl</th>
        <th class="sub-header">PnL</th><th class="sub-header">MaxDD</th><th class="sub-header">1k Gap</th><th class="sub-header">1k Lvl</th>
    </tr>
</thead>
<tbody>
"""
    for i, item in enumerate(data, 1):
        initial_lot = item['InitialLot']
        orig_pnl = item['TotalProfit']
        orig_dd = item['MaxDD']
        max_trades = item.get('MaxTrades', 'N/A')
        max_trades_gap = item.get('MaxTradesGap', 'N/A')
        report_file = item['ReportFile']
        report_link = item.get('ReportLink', '')
        
        display_file = f"<a href='{report_link}' target='_blank'>{report_file}</a>" if report_link else report_file
        
        html += f"<tr>\n"
        html += f"<td>{i}</td><td>{item['Symbol']}</td><td>{display_file}</td>"
        html += f"<td>{max_trades}</td><td>{max_trades_gap}</td>"
        
        for lot in sim_lots:
            multiplier = lot / initial_lot if initial_lot > 0 else 0
            sim_pnl = orig_pnl * multiplier
            sim_dd = orig_dd * multiplier
            
            sim_1k = item['Sim1kData'].get(lot, {'gap': 'N/A', 'level': 'N/A'})
            
            html += f"<td><span class='profit'>{sim_pnl:.2f}</span></td>"
            html += f"<td><span class='drawdown'>{sim_dd:.2f}</span></td>"
            html += f"<td><span class='threshold'>{sim_1k['gap']}</span></td>"
            html += f"<td><span class='threshold'>{sim_1k['level']}</span></td>"
        
        html += "</tr>\n"

    # Total Row (PnL and DD only)
    html += "<tr><td colspan='5'><b>TOTAL</b></td>"
    
    for lot in sim_lots:
        sim_total_pnl = sum(item['TotalProfit'] * (lot / item['InitialLot'] if item['InitialLot'] > 0 else 0) for item in data)
        sim_total_dd = sum(item['MaxDD'] * (lot / item['InitialLot'] if item['InitialLot'] > 0 else 0) for item in data)
        html += f"<td><b>{sim_total_pnl:.2f}</b></td><td><b>{sim_total_dd:.2f}</b></td><td colspan='2' style='background:#f9f9f9;'></td>"
    
    html += """
</tbody>
</table>
</body>
</html>
"""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Simulation report generated: {output_path}")

def main():
    parser = argparse.ArgumentParser(description='Simulate results with different Lot Sizes')
    parser.add_argument('directory', type=str, help='Directory containing Full_Analysis.html')
    args = parser.parse_args()

    html_path = os.path.join(args.directory, "Full_Analysis.html")
    sim_path = os.path.join(args.directory, "sim.html")

    data = parse_full_analysis(html_path)
    if data:
        generate_sim_html(data, sim_path)
        
        # Automatically open in default browser
        try:
            clickable_link = f"file:///{os.path.abspath(sim_path).replace(os.sep, '/')}"
            print(f"Opening Simulation Report: {clickable_link}")
            webbrowser.open(clickable_link)
        except Exception as e:
            print(f"Could not automatically open browser: {e}")
    else:
        print("Failed to extract data from Full_Analysis.html")

if __name__ == "__main__":
    main()

import os
import argparse
import pandas as pd
from bs4 import BeautifulSoup
import re

def filter_report():
    parser = argparse.ArgumentParser(description='Filter analysis report by top N profitable files.')
    parser.add_argument('output_dir', type=str, help='Path to the output directory containing Short_Analysis.html and report_list.csv')
    parser.add_argument('n', type=int, help='Number of top profitable files to select')
    args = parser.parse_args()

    output_dir = os.path.abspath(args.output_dir)
    short_report_path = os.path.join(output_dir, "Short_Analysis.html")
    report_list_path = os.path.join(output_dir, "report_list.csv")
    filtered_report_path = os.path.join(output_dir, "Filtered Report.html")
    filtered_csv_path = os.path.join(output_dir, "report_list.filtered.csv")

    if not os.path.exists(short_report_path):
        print(f"Error: Short_Analysis.html not found in {output_dir}")
        return
    if not os.path.exists(report_list_path):
        print(f"Error: report_list.csv not found in {output_dir}")
        return

    print(f"Filtering top {args.n} files from {short_report_path}...")

    with open(short_report_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')

    # 1. Selection: Parse Monthly Contributor Breakdown
    h2_contributor = soup.find(['h2', 'h3'], string=lambda t: t and 'Monthly Contributor Breakdown' in t)
    if not h2_contributor:
        h2_contributor = soup.find(lambda tag: tag.name in ['h2', 'h3'] and 'Monthly Contributor Breakdown' in tag.get_text())
    
    if not h2_contributor:
        print("Error: Could not find Monthly Contributor Breakdown section.")
        return

    table = h2_contributor.find_next('table')
    if not table:
        print("Error: Could not find table after Monthly Contributor Breakdown header.")
        return

    rows = table.find_all('tr')[1:] # Skip header
    all_contributors = []
    
    for row in rows:
        if "Total" in row.get_text():
            continue
        cols = row.find_all('td')
        if len(cols) < 6: continue
        
        # Symbol is 2nd col (index 1)
        symbol = cols[1].get_text(strip=True)
        # Report File is 3rd col (index 2)
        code_tag = cols[2].find('code')
        if not code_tag:
            name = cols[2].get_text(strip=True)
        else:
            name = code_tag.get_text(strip=True)
            
        # Total Profit is the last col
        try:
            total_profit = float(cols[-1].get_text(strip=True).replace(',', ''))
        except ValueError:
            total_profit = 0.0
            
        # Extract monthly data for later use in table recreation
        # Monthly data starts from 6th col (index 5) up to the second to last col
        monthly_values = [col.get_text(strip=True) for col in cols[5:-1]]
        
        # Also need Buy/Sell trades
        buy_trades = int(cols[3].get_text(strip=True))
        sell_trades = int(cols[4].get_text(strip=True))
        
        all_contributors.append({
            'symbol': symbol,
            'name': name,
            'total_profit': total_profit,
            'row_html': row,
            'monthly_values': monthly_values,
            'buy_trades': buy_trades,
            'sell_trades': sell_trades
        })

    # Sort and select top N
    all_contributors.sort(key=lambda x: x['total_profit'], reverse=True)
    selected = all_contributors[:args.n]
    selected_names = set(x['name'] for x in selected)

    print(f"Selected files: {', '.join(selected_names)}")

    # 2. Recreate report_list.filtered.csv
    df_list = pd.read_csv(report_list_path)
    df_list['Include'] = df_list['FilePath'].apply(lambda x: 1 if os.path.basename(x) in selected_names else 0)
    df_list.to_csv(filtered_csv_path, index=False)
    print(f"Created {filtered_csv_path}")

    # 3. Construct Filtered Report.html
    # Recalculate Summary
    total_selected_profit = sum(x['total_profit'] for x in selected)
    total_selected_trades = sum(x['buy_trades'] + x['sell_trades'] for x in selected)
    total_selected_buy = sum(x['buy_trades'] for x in selected)
    total_selected_sell = sum(x['sell_trades'] for x in selected)
    
    # Try to get base capital from summary box
    summary_box = soup.find('div', class_='summary-box')
    base_capital = 100000.0 # Default
    if summary_box:
        base_match = re.search(r'Base Capital:</strong>\s*([\d,.]+)', str(summary_box))
        if base_match:
            base_capital = float(base_match.group(1).replace(',', ''))
    
    final_balance = base_capital + total_selected_profit

    # Create new soup or modify
    new_soup = BeautifulSoup("<!DOCTYPE html><html lang='en'></html>", 'html.parser')
    new_soup.html.append(soup.head)
    body = new_soup.new_tag('body')
    new_soup.html.append(body)

    body.append(new_soup.new_tag('h1'))
    body.h1.string = "Filtered Portfolio Analysis Report"

    # New Summary Box
    new_summary = new_soup.new_tag('div', attrs={'class': 'summary-box'})
    # Extract Period from original
    period_p = soup.find('p', string=lambda t: t and 'Period:' in t)
    if period_p:
        new_summary.append(period_p)
    
    p_reports = new_soup.new_tag('p')
    p_reports.append(new_soup.new_tag('strong'))
    p_reports.strong.string = "Included Reports: "
    p_reports.append(f"{len(selected)} / {len(all_contributors)}")
    new_summary.append(p_reports)

    p_base = new_soup.new_tag('p')
    p_base.append(new_soup.new_tag('strong'))
    p_base.strong.string = "Base Capital: "
    p_base.append(f"{base_capital:,.2f}")
    new_summary.append(p_base)

    p_balance = new_soup.new_tag('p')
    p_balance.append(new_soup.new_tag('strong'))
    p_balance.strong.string = "Final Balance: "
    p_balance.append(f"{final_balance:,.2f}")
    new_summary.append(p_balance)

    p_profit = new_soup.new_tag('p')
    p_profit.append(new_soup.new_tag('strong'))
    p_profit.strong.string = "Total Profit: "
    p_profit.append(f"{total_selected_profit:,.2f}")
    new_summary.append(p_profit)

    p_trades = new_soup.new_tag('p')
    p_trades.append(new_soup.new_tag('strong'))
    p_trades.strong.string = "Total Trades: "
    p_trades.append(f"{total_selected_trades} (Buy: {total_selected_buy}, Sell: {total_selected_sell})")
    new_summary.append(p_trades)
    
    body.append(new_summary)

    # NO PERFORMANCE CHARTS (as requested)

    # Monthly Contributor Breakdown
    h2_cont = new_soup.new_tag('h2')
    h2_cont.string = "Monthly Contributor Breakdown"
    body.append(h2_cont)

    # Recreate Table
    new_table = new_soup.new_tag('table')
    thead = new_soup.new_tag('thead')
    new_table.append(thead)
    orig_thead = table.find('thead')
    if orig_thead:
        thead.append(orig_thead.find('tr'))
    
    tbody = new_soup.new_tag('tbody')
    new_table.append(tbody)
    
    # Track monthly totals for the footer
    header_cols = [th.get_text(strip=True) for th in thead.find_all('th')]
    month_indices = [i for i, h in enumerate(header_cols) if h not in ['S.No', 'Symbol', 'Report File', 'Buy Trades', 'Sell Trades', 'Total']]
    monthly_totals = [0.0] * len(month_indices)

    for i, item in enumerate(selected, 1):
        # Update S.No
        new_row = BeautifulSoup(str(item['row_html']), 'html.parser').tr
        new_row.find('td').string = str(i)
        tbody.append(new_row)
        
        # Accumulate monthly totals
        for m_idx, col_idx in enumerate(month_indices):
            try:
                val = float(item['monthly_values'][m_idx].replace(',', ''))
                monthly_totals[m_idx] += val
            except:
                pass

    # Add Total Row
    total_row = new_soup.new_tag('tr')
    td_label = new_soup.new_tag('td', attrs={'colspan': '3'})
    td_label.append(new_soup.new_tag('b'))
    td_label.b.string = "Total"
    total_row.append(td_label)
    
    td_buy = new_soup.new_tag('td', attrs={'style': 'text-align:right;'})
    td_buy.append(new_soup.new_tag('b'))
    td_buy.b.string = str(total_selected_buy)
    total_row.append(td_buy)
    
    td_sell = new_soup.new_tag('td', attrs={'style': 'text-align:right;'})
    td_sell.append(new_soup.new_tag('b'))
    td_sell.b.string = str(total_selected_sell)
    total_row.append(td_sell)
    
    for m_val in monthly_totals:
        td_m = new_soup.new_tag('td', attrs={'style': 'text-align:right;'})
        td_m.append(new_soup.new_tag('b'))
        td_m.b.string = f"{m_val:.2f}"
        total_row.append(td_m)
        
    td_gt = new_soup.new_tag('td', attrs={'style': 'text-align:right;'})
    td_gt.append(new_soup.new_tag('b'))
    td_gt.b.string = f"{total_selected_profit:.2f}"
    total_row.append(td_gt)
    
    tbody.append(total_row)
    body.append(new_table)

    # Monthly Currency Breakdown
    h2_curr = new_soup.new_tag('h2')
    h2_curr.string = "Monthly Currency Breakdown"
    body.append(h2_curr)
    
    # Recalculate currency breakdown
    symbol_data = {}
    for item in selected:
        sym = item['symbol']
        if sym not in symbol_data:
            symbol_data[sym] = {
                'count': 0,
                'buy': 0,
                'sell': 0,
                'monthly': [0.0] * len(month_indices),
                'total': 0.0
            }
        symbol_data[sym]['count'] += 1
        symbol_data[sym]['buy'] += item['buy_trades']
        symbol_data[sym]['sell'] += item['sell_trades']
        symbol_data[sym]['total'] += item['total_profit']
        for m_idx in range(len(month_indices)):
            try:
                val = float(item['monthly_values'][m_idx].replace(',', ''))
                symbol_data[sym]['monthly'][m_idx] += val
            except:
                pass
                
    curr_table = new_soup.new_tag('table')
    curr_thead = new_soup.new_tag('thead')
    curr_row = new_soup.new_tag('tr')
    for h in ['S.No', 'Symbol', 'Report File Count', 'Buy Trades', 'Sell Trades'] + [header_cols[mi] for mi in month_indices] + ['Total']:
        th = new_soup.new_tag('th')
        th.string = h
        curr_row.append(th)
    curr_thead.append(curr_row)
    curr_table.append(curr_thead)
    
    curr_tbody = new_soup.new_tag('tbody')
    for i, (sym, data) in enumerate(sorted(symbol_data.items()), 1):
        tr = new_soup.new_tag('tr')
        tr.append(new_soup.new_tag('td'))
        tr.td.string = str(i)
        tr.append(new_soup.new_tag('td'))
        tr.find_all('td')[1].string = sym
        tr.append(new_soup.new_tag('td', attrs={'style': 'text-align:right;'}))
        tr.find_all('td')[2].string = str(data['count'])
        tr.append(new_soup.new_tag('td', attrs={'style': 'text-align:right;'}))
        tr.find_all('td')[3].string = str(data['buy'])
        tr.append(new_soup.new_tag('td', attrs={'style': 'text-align:right;'}))
        tr.find_all('td')[4].string = str(data['sell'])
        
        for m_val in data['monthly']:
            td = new_soup.new_tag('td', attrs={'style': 'text-align:right;'})
            td.string = f"{m_val:.2f}"
            tr.append(td)
            
        td_t = new_soup.new_tag('td', attrs={'style': 'text-align:right;'})
        td_t.append(new_soup.new_tag('b'))
        td_t.b.string = f"{data['total']:.2f}"
        tr.append(td_t)
        curr_tbody.append(tr)
        
    # Total row for currency
    curr_total_row = new_soup.new_tag('tr')
    tr_l = new_soup.new_tag('td', attrs={'colspan': '2'})
    tr_l.append(new_soup.new_tag('b'))
    tr_l.b.string = "Total"
    curr_total_row.append(tr_l)
    
    tr_c = new_soup.new_tag('td', attrs={'style': 'text-align:right;'})
    tr_c.append(new_soup.new_tag('b'))
    tr_c.b.string = str(len(selected))
    curr_total_row.append(tr_c)
    
    tr_bi = new_soup.new_tag('td', attrs={'style': 'text-align:right;'})
    tr_bi.append(new_soup.new_tag('b'))
    tr_bi.b.string = str(total_selected_buy)
    curr_total_row.append(tr_bi)
    
    tr_si = new_soup.new_tag('td', attrs={'style': 'text-align:right;'})
    tr_si.append(new_soup.new_tag('b'))
    tr_si.b.string = str(total_selected_sell)
    curr_total_row.append(tr_si)
    
    for m_val in monthly_totals:
        td = new_soup.new_tag('td', attrs={'style': 'text-align:right;'})
        td.append(new_soup.new_tag('b'))
        td.b.string = f"{m_val:.2f}"
        curr_total_row.append(td)
        
    tr_gt = new_soup.new_tag('td', attrs={'style': 'text-align:right;'})
    tr_gt.append(new_soup.new_tag('b'))
    tr_gt.b.string = f"{total_selected_profit:.2f}"
    curr_total_row.append(tr_gt)
    curr_tbody.append(curr_total_row)
    
    curr_table.append(curr_tbody)
    body.append(curr_table)

    # Detailed Per-Report Analysis
    h2_detail = new_soup.new_tag('h2')
    h2_detail.string = "Detailed Per-Report Analysis"
    body.append(h2_detail)
    
    # Extract only relevant h3 sections
    # They usually start with <h3>Report: ...</h3>
    for h3 in soup.find_all('h3'):
        h3_text = h3.get_text()
        if "Report:" in h3_text:
            code_tag = h3.find('code')
            if not code_tag:
                code_tag = h3.find('a')
            
            if code_tag:
                name = code_tag.get_text(strip=True)
                if name in selected_names:
                    body.append(h3)
                    # Get all siblings until next h3 or h2
                    curr = h3.next_sibling
                    while curr and curr.name not in ['h3', 'h2']:
                        next_s = curr.next_sibling
                        body.append(curr)
                        curr = next_s

    with open(filtered_report_path, 'w', encoding='utf-8') as f:
        f.write(new_soup.prettify())
    
    print(f"Generated {filtered_report_path}")

if __name__ == "__main__":
    filter_report()

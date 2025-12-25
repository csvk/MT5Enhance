import pandas as pd
import os
import glob
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import argparse
from datetime import datetime
import numpy as np

def main():
    parser = argparse.ArgumentParser(description='Comprehensive Portfolio Analysis')
    parser.add_argument('output_folder', type=str, help='Path to the output folder created in Step 1 (e.g., analysis/output_*).')
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--base', type=float, default=100000.0, help='Base capital (default: 100,000)')
    args = parser.parse_args()

    output_dir = os.path.abspath(args.output_folder)

    # 1. Locate Trades folder
    trades_folder = os.path.join(output_dir, "Trades")
    if not os.path.exists(trades_folder):
        print(f"Error: Trades folder not found in {output_dir}")
        return
    
    print(f"Using trades folder: {trades_folder}")

    # 2. Load all deals
    csv_files = glob.glob(os.path.join(trades_folder, "selected_trades_*.csv"))
    if not csv_files:
        print("No CSV files found in the trades folder.")
        return

    all_deals = []
    for f in csv_files:
        df = pd.read_csv(f)
        df['Time'] = pd.to_datetime(df['Time'])
        all_deals.append(df)
    
    df_deals = pd.concat(all_deals).sort_values('Time')

    # 3. Determine Date Range
    data_start = df_deals['Time'].min().normalize()
    data_end = df_deals['Time'].max().normalize() + pd.Timedelta(days=1)
    
    calc_start = pd.to_datetime(args.start) if args.start else data_start
    calc_end = pd.to_datetime(args.end) if args.end else data_end

    print(f"Analysis range: {calc_start.date()} to {calc_end.date()}")

    # 4. Filter deals by date range
    df_deals = df_deals[(df_deals['Time'] >= calc_start) & (df_deals['Time'] < calc_end)]

    if df_deals.empty:
        print("No trades found in the specified date range.")
        return

    # 5. Create Portfolio Timeline
    # We create a 1-minute grid
    full_idx = pd.date_range(start=calc_start, end=calc_end, freq='1min')
    portfolio = pd.DataFrame(index=full_idx)
    portfolio['BalancePnL'] = 0.0

    # Group deals by minute to avoid duplicates on the grid
    deals_grouped = df_deals.copy()
    deals_grouped['Time'] = deals_grouped['Time'].dt.floor('1min')
    
    # Balance changes only at exit ('out' or 'in/out')
    balance_deals = deals_grouped[deals_grouped['Direction'].str.lower().isin(['out', 'in/out'])]
    balance_changes = balance_deals.groupby('Time')['DealPnL'].sum()

    # Map to grid
    portfolio.loc[balance_changes.index, 'BalancePnL'] = balance_changes.values

    # Cumulative Sums
    portfolio['Balance'] = portfolio['BalancePnL'].cumsum() + args.base

    # 6. Drawdown Calculation (Underwater)
    portfolio['PeakBalance'] = portfolio['Balance'].expanding().max()
    portfolio['Drawdown'] = (portfolio['Balance'] / portfolio['PeakBalance']) - 1
    # Note: Using Balance for drawdown as is typical.
    portfolio['Drawdown%'] = portfolio['Drawdown'] * 100

    # 7. Charting
    def add_monthly_grids(ax, start, end):
        # Add vertical lines at start of each month
        months = pd.date_range(start=start.replace(day=1), end=end, freq='MS')
        for m in months:
            ax.axvline(m, color='gray', linestyle='--', alpha=0.5, linewidth=0.8)

    # Chart 1: Portfolio (Balance)
    fig1, ax1 = plt.subplots(figsize=(15, 8))
    ax1.plot(portfolio.index, portfolio['Balance'], label='Balance', color='blue', linewidth=1.5)
    ax1.set_title('Portfolio Performance (Balance)')
    ax1.set_ylabel('Amount')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    add_monthly_grids(ax1, calc_start, calc_end)
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format(int(x), ',')))
    plt.tight_layout()
    chart1_path = os.path.join(output_dir, "Portfolio_Chart.png")
    plt.savefig(chart1_path)
    plt.close()

    # Chart 2: Underwater Drawdown
    fig2, ax2 = plt.subplots(figsize=(15, 6))
    ax2.fill_between(portfolio.index, portfolio['Drawdown%'], 0, color='red', alpha=0.3)
    ax2.plot(portfolio.index, portfolio['Drawdown%'], color='red', linewidth=0.8)
    ax2.set_title('Underwater Drawdown')
    ax2.set_ylabel('Drawdown %')
    ax2.grid(True, alpha=0.3)
    add_monthly_grids(ax2, calc_start, calc_end)

    # Add secondary Y-axis for absolute drawdown values
    ax2_abs = ax2.twinx()
    # Calculate absolute drawdown (Balance - PeakBalance)
    abs_drawdown = portfolio['Balance'] - portfolio['PeakBalance']
    ax2_abs.plot(portfolio.index, abs_drawdown, alpha=0) # Invisible plot just to set the scale
    ax2_abs.set_ylabel('Drawdown Absolute')
    ax2_abs.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format(int(x), ',')))

    plt.tight_layout()
    chart2_path = os.path.join(output_dir, "Drawdown_Chart.png")
    plt.savefig(chart2_path)
    plt.close()

    # 8. Consolidated Monthly Contributor Table (with Gradient Color Coding)
    df_deals['Month'] = df_deals['Time'].dt.to_period('M')
    # Group by File, Symbol, and Month
    file_monthly_pnl = df_deals.groupby(['SourceFile', 'Symbol', 'Month'])['DealPnL'].sum().reset_index()
    
    # Pivot to get months as columns, keep SourceFile and Symbol as indices
    pivot_table = file_monthly_pnl.pivot(index=['Symbol', 'SourceFile'], columns='Month', values='DealPnL').fillna(0)
    
    # Sort by Symbol (which is the first level of the index) then SourceFile
    pivot_table = pivot_table.sort_index(level=['Symbol', 'SourceFile'])

    def get_color(val, min_val, max_val):
        if val == 0: return "#ffffff" # White for zero
        if val > 0:
            # Green gradient
            alpha = min(val / (max_val if max_val > 0 else 1), 1)
            r = int(255 - (255 - 34) * alpha)
            g = int(255 - (255 - 197) * alpha)
            b = int(255 - (255 - 94) * alpha)
            return f"#{r:02x}{g:02x}{b:02x}"
        else:
            # Red gradient
            alpha = min(abs(val) / (abs(min_val) if min_val < 0 else 1), 1)
            r = int(255 - (255 - 239) * alpha)
            g = int(255 - (255 - 68) * alpha)
            b = int(255 - (255 - 68) * alpha)
            return f"#{r:02x}{g:02x}{b:02x}"

    # Calculate global min/max for the gradient scale
    all_values = pivot_table.values.flatten()
    global_min = all_values.min()
    global_max = all_values.max()

    months_headers = [str(m) for m in pivot_table.columns]
    
    table_html = "## Monthly Contributor Breakdown\n\n"
    table_html += "<table>\n<thead>\n<tr>"
    table_html += "<th>S.No</th><th>Symbol</th><th>Report File</th>" + "".join([f"<th>{m}</th>" for m in months_headers]) + "<th>Total</th>"
    table_html += "</tr>\n</thead>\n<tbody>\n"
    
    for i, ((symbol, file_name), row) in enumerate(pivot_table.iterrows(), 1):
        table_html += "<tr>"
        table_html += f"<td>{i}</td>"
        table_html += f"<td>{symbol}</td>"
        table_html += f"<td><code>{file_name}</code></td>"
        for val in row:
            color = get_color(val, global_min, global_max)
            table_html += f'<td style="background-color:{color}; color:black; text-align:right;">{val:.2f}</td>'
        
        total_pnl = row.sum()
        total_color = get_color(total_pnl, pivot_table.sum(axis=1).min(), pivot_table.sum(axis=1).max())
        table_html += f'<td style="background-color:{total_color}; color:black; text-align:right;"><b>{total_pnl:.2f}</b></td>'
        table_html += "</tr>\n"
    
    # Total row
    monthly_totals = pivot_table.sum()
    grand_total = monthly_totals.sum()
    table_html += "<tr>"
    table_html += "<td colspan='3'><b>Total</b></td>"
    for val in monthly_totals:
        color = get_color(val, monthly_totals.min(), monthly_totals.max())
        table_html += f'<td style="background-color:{color}; color:black; text-align:right;"><b>{val:.2f}</b></td>'
    
    gt_color = get_color(grand_total, pivot_table.values.sum(), pivot_table.values.sum())
    table_html += f'<td style="background-color:{gt_color}; color:black; text-align:right;"><b>{grand_total:.2f}</b></td>'
    table_html += "</tr>\n</tbody>\n</table>\n\n"

    # 9. Compile Markdown Report
    num_included = df_deals['SourceFile'].nunique()
    
    # Try to find the total number of files and skipped files from report_list_<timestamp>.csv
    num_total = "Unknown"
    explicitly_skipped = []
    overlapping_skipped = []
    
    report_list_path = os.path.join(output_dir, "report_list.csv")
    if os.path.exists(report_list_path):
        try:
            df_list = pd.read_csv(report_list_path)
            num_total = len(df_list)
            
            # Categorize skipped files
            actually_included = set(df_deals['SourceFile'].unique())
            
            explicitly_excluded_paths = df_list[df_list['Include'] == 0]['FilePath']
            explicitly_skipped = sorted([os.path.basename(f) for f in explicitly_excluded_paths])
            
            potentially_included_paths = df_list[df_list['Include'] == 1]['FilePath']
            potentially_included = set(os.path.basename(f) for f in potentially_included_paths)
            
            overlapping_skipped = sorted(list(potentially_included - actually_included))
        except:
            pass

    report_path = os.path.join(output_dir, "Full_Analysis.md")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("# Portfolio Analysis Report\n\n")
        f.write(f"**Period:** {calc_start.date()} to {calc_end.date()}\n")
        f.write(f"**Included Reports:** {num_included} / {num_total}\n")
        f.write(f"**Base Capital:** {args.base:,.2f}\n")
        f.write(f"**Final Balance:** {portfolio['Balance'].iloc[-1]:,.2f}\n")
        f.write(f"**Total Profit:** {(portfolio['Balance'].iloc[-1] - args.base):,.2f}\n\n")
        
        f.write("## Performance Charts\n\n")
        f.write("![Portfolio Chart](Portfolio_Chart.png)\n\n")
        f.write("![Drawdown Chart](Drawdown_Chart.png)\n\n")
        
        f.write(table_html)

        if explicitly_skipped:
            f.write("## Explicitly Excluded Reports\n\n")
            f.write("These files were skipped because they were marked with `Include = 0` in the report list:\n\n")
            for sf in explicitly_skipped:
                f.write(f"- `{sf}`\n")
            f.write("\n")

        if overlapping_skipped:
            f.write("## Overlapping Trades (Skipped)\n\n")
            f.write("These files were marked for inclusion but skipped because all their trades overlapped with already accepted sequences:\n\n")
            for sf in overlapping_skipped:
                f.write(f"- `{sf}`\n")
            f.write("\n")

if __name__ == "__main__":
    main()

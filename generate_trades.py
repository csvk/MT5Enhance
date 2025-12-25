import pandas as pd
import os
import shutil
import glob
from bs4 import BeautifulSoup
import io
import argparse
from datetime import datetime

def parse_sequences_and_deals(file_path):
    try:
        with open(file_path, 'r', encoding='utf-16', errors='ignore') as f:
            content = f.read()
            
        soup = BeautifulSoup(content, 'lxml')
        tables = soup.find_all('table')
        
        if len(tables) < 2:
            return []
            
        deals_table = tables[1]
        dfs = pd.read_html(io.StringIO(str(deals_table)), header=0)
        
        if not dfs:
            return []
            
        df = dfs[0].copy()
        
        # Standardize columns
        if len(df.columns) == 13:
            df.columns = ['Time', 'Deal', 'Symbol', 'Type', 'Direction', 'Volume', 'Price', 'Order', 'Commission', 'Swap', 'Profit', 'Balance', 'Comment']
            if str(df.iloc[0]['Time']).strip() == 'Time':
                df = df.iloc[1:]
        else:
            first_row = df.iloc[0].astype(str).tolist()
            if any('Time' in x for x in first_row) and any('Balance' in x for x in first_row):
                df.columns = first_row
                df = df.iloc[1:]
            
            df.columns = df.columns.astype(str).str.strip()
            time_col = next((c for c in df.columns if 'Time' in c), None)
            if time_col: df.rename(columns={time_col: 'Time'}, inplace=True)

        df['Time'] = pd.to_datetime(df['Time'], format='%Y.%m.%d %H:%M:%S', errors='coerce')
        df = df.dropna(subset=['Time'])
        
        # Clean numeric columns
        cols_to_sum = ['Profit', 'Commission', 'Swap']
        for c in cols_to_sum:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c].astype(str).str.replace(' ', ''), errors='coerce').fillna(0)
        
        df['DealPnL'] = df[cols_to_sum].sum(axis=1)
        df = df.sort_values('Time')
        
        sequences = []
        current_seq_deals = []
        open_volume = 0.0
        
        for idx, row in df.iterrows():
            direction = str(row['Direction']).strip().lower()
            try:
                vol = float(row['Volume'])
            except:
                vol = 0.0
                
            if direction == 'in':
                if open_volume < 0.000001:
                    current_seq_deals = [row.to_dict()]
                else:
                    current_seq_deals.append(row.to_dict())
                open_volume += vol
                
            elif direction == 'out':
                current_seq_deals.append(row.to_dict())
                open_volume -= vol
                if open_volume < 0.000001:
                    open_volume = 0.0
                    if current_seq_deals:
                        sequences.append({
                            'start': pd.to_datetime(current_seq_deals[0]['Time']),
                            'end': pd.to_datetime(row['Time']),
                            'deals': current_seq_deals,
                            'symbol': str(row['Symbol']),
                            'file': os.path.basename(file_path)
                        })
                        current_seq_deals = []
            
            elif direction == 'in/out':
                current_seq_deals.append(row.to_dict())
                
        return sequences

    except Exception as e:
        print(f"Error parsing {os.path.basename(file_path)}: {e}")
        return []

def main():
    parser = argparse.ArgumentParser(description='Extract Non-Overlapping Trades to CSV')
    parser.add_argument('output_folder', type=str, help='Path to the output folder created in Step 1 (e.g., analysis/output_*).')
    parser.add_argument('--base', type=float, default=100000.0, help='Base capital for each symbol (default: 100,000)')
    args = parser.parse_args()

    output_dir = os.path.abspath(args.output_folder)
    csv_path = os.path.join(output_dir, "report_list.csv")

    if not os.path.exists(csv_path):
        print(f"Error: report_list.csv not found in {output_dir}")
        print("Please ensure you provided the correct output folder path.")
        return

    df_list = pd.read_csv(csv_path)
    included_files = df_list[df_list['Include'] == 1]['FilePath'].tolist()

    if not included_files:
        print("No files marked for inclusion.")
        return

    print(f"Processing {len(included_files)} reports...")
    
    all_sequences = []
    for f in included_files:
        all_sequences.extend(parse_sequences_and_deals(f))
        
    # Group by Symbol
    sequences_by_symbol = {}
    for s in all_sequences:
        sym = s['symbol']
        if sym not in sequences_by_symbol:
            sequences_by_symbol[sym] = []
        sequences_by_symbol[sym].append(s)
        
    # Apply non-overlapping logic per symbol
    trades_out_dir = os.path.join(output_dir, "Trades")
    
    # Refresh directory: Delete if exists, then recreate
    if os.path.exists(trades_out_dir):
        print(f"Refreshing directory: {trades_out_dir}")
        shutil.rmtree(trades_out_dir)
    os.makedirs(trades_out_dir, exist_ok=True)
    
    total_trades = 0
    for sym, seqs in sequences_by_symbol.items():
        seqs.sort(key=lambda x: x['start'])
        last_end_time = pd.Timestamp.min
        accepted_deals = []
        
        current_balance = args.base
        
        for s in seqs:
            if s['start'] > last_end_time:
                # Add all deals in this sequence
                for d in s['deals']:
                    d['SourceFile'] = s['file']
                    direction = str(d.get('Direction', '')).strip().lower()
                    
                    if direction == 'in':
                        # Entry: Balance is the same as the current (previous) balance
                        d['Balance'] = current_balance
                    else:
                        # Exit (out or in/out): Balance is updated by DealPnL
                        current_balance += d.get('DealPnL', 0.0)
                        d['Balance'] = current_balance
                    
                    accepted_deals.append(d)
                
                last_end_time = s['end']
                total_trades += 1

        if accepted_deals:
            out_csv = os.path.join(trades_out_dir, f"selected_trades_{sym}.csv")
            pd.DataFrame(accepted_deals).to_csv(out_csv, index=False)

    print(f"Extracted {total_trades} non-overlapping trades.")
    print(f"Deals saved to: {trades_out_dir}")

if __name__ == "__main__":
    main()

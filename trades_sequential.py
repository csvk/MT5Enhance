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
            return [], []
            
        deals_table = tables[1]
        dfs = pd.read_html(io.StringIO(str(deals_table)), header=0)
        
        if not dfs:
            return [], []
            
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
        cols_to_sum = ['Profit', 'Commission', 'Swap', 'Balance']
        for c in cols_to_sum:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c].astype(str).str.replace(' ', ''), errors='coerce').fillna(0)
        
        df = df.sort_values('Time')
        
        # Filter for actual deals and balance rows
        df['Direction_dt'] = df['Direction'].astype(str).str.strip().str.lower()
        df['Type_dt'] = df['Type'].astype(str).str.strip().str.lower()
        
        valid_directions = ['in', 'out', 'in/out']
        df = df[(df['Direction_dt'].isin(valid_directions)) | (df['Type_dt'] == 'balance')].copy()
        
        # Remove helper columns before processing
        df.drop(columns=['Direction_dt', 'Type_dt'], inplace=True)
        
        sequences = []
        long_vol = 0.0
        short_vol = 0.0
        active_long_deals = []
        active_short_deals = []
        long_seq_num = None
        short_seq_num = None
        long_trade_count = 0
        short_trade_count = 0
        
        global_seq_counter = 0
        all_deals_output = []
        
        for idx, row in df.iterrows():
            type_val = str(row['Type']).strip().lower()
            direction = str(row['Direction']).strip().lower()
            try:
                vol = float(row['Volume'])
            except:
                vol = 0.0
            
            row_dict = row.to_dict()
            row_dict['SourceFile'] = os.path.basename(file_path)
            row_dict['SequenceNumber'] = 0
            row_dict['TradeNumberInSequence'] = 0
            
            # --- Long Side Logic ---
            if (type_val == 'buy' and direction == 'in') or (type_val == 'sell' and direction == 'out' and long_vol > 0.000001):
                if direction == 'in':
                    if long_vol < 0.000001:
                        global_seq_counter += 1
                        long_seq_num = global_seq_counter
                        long_trade_count = 1
                        active_long_deals = []
                    else:
                        long_trade_count += 1
                    long_vol += vol
                    row_dict['TradeNumberInSequence'] = long_trade_count
                else: # out
                    long_vol -= vol
                    # No increment, and set to blank for 'out'
                    row_dict['TradeNumberInSequence'] = None
                
                row_dict['SequenceNumber'] = long_seq_num
                active_long_deals.append(row_dict)
                
                if long_vol < 0.000001:
                    if active_long_deals:
                        sequences.append({
                            'start': pd.to_datetime(active_long_deals[0]['Time']),
                            'end': pd.to_datetime(row['Time']),
                            'deals': active_long_deals.copy(),
                            'symbol': str(row['Symbol']),
                            'file': os.path.basename(file_path),
                            'side': 'long'
                        })
                    long_vol = 0.0
                    long_seq_num = None
            
            # --- Short Side Logic ---
            elif (type_val == 'sell' and direction == 'in') or (type_val == 'buy' and direction == 'out' and short_vol > 0.000001):
                if direction == 'in':
                    if short_vol < 0.000001:
                        global_seq_counter += 1
                        short_seq_num = global_seq_counter
                        short_trade_count = 1
                        active_short_deals = []
                    else:
                        short_trade_count += 1
                    short_vol += vol
                    row_dict['TradeNumberInSequence'] = short_trade_count
                else: # out
                    short_vol -= vol
                    # No increment, and set to blank for 'out'
                    row_dict['TradeNumberInSequence'] = None
                
                row_dict['SequenceNumber'] = short_seq_num
                active_short_deals.append(row_dict)
                
                if short_vol < 0.000001:
                    if active_short_deals:
                        sequences.append({
                            'start': pd.to_datetime(active_short_deals[0]['Time']),
                            'end': pd.to_datetime(row['Time']),
                            'deals': active_short_deals.copy(),
                            'symbol': str(row['Symbol']),
                            'file': os.path.basename(file_path),
                            'side': 'short'
                        })
                    short_vol = 0.0
                    short_seq_num = None

            # --- In/Out Logic (Reversal/Exit part) ---
            elif direction == 'in/out':
                # Treat in/out as an exit for counting purposes (TradeNumberInSequence blank)
                if long_vol > 0.000001:
                    row_dict['SequenceNumber'] = long_seq_num
                    row_dict['TradeNumberInSequence'] = None
                    active_long_deals.append(row_dict)
                elif short_vol > 0.000001:
                    row_dict['SequenceNumber'] = short_seq_num
                    row_dict['TradeNumberInSequence'] = None
                    active_short_deals.append(row_dict)

            all_deals_output.append(row_dict)
                
        return sequences, all_deals_output

    except Exception as e:
        print(f"Error parsing {os.path.basename(file_path)}: {e}")
        return [], []

def main():
    parser = argparse.ArgumentParser(description='Extract Non-Overlapping Trades to CSV')
    parser.add_argument('output_folder', type=str, help='Path to the output folder (e.g., [Parent]/analysis/output_*) created in Step 1.')
    parser.add_argument('--base', type=float, default=100000.0, help='Base capital for each symbol (default: 100,000)')
    parser.add_argument('--all', action='store_true', help='Process all reports for trade extraction, even if excluded from portfolio.')
    args = parser.parse_args()

    output_dir = os.path.abspath(args.output_folder)
    csv_path = os.path.join(output_dir, "report_list.csv")

    if not os.path.exists(csv_path):
        print(f"Error: report_list.csv not found in {output_dir}")
        print("Please ensure you provided the correct output folder path.")
        return

    df_list = pd.read_csv(csv_path)
    
    # Identify included files
    included_files_set = set(df_list[df_list['Include'] == 1]['FilePath'].tolist())
    
    # Determine which files to process for trade extraction
    if args.all:
        all_files_to_process = df_list['FilePath'].tolist()
        print("Flag --all detected: Processing ALL reports for trade extraction.")
    else:
        all_files_to_process = df_list[df_list['Include'] == 1]['FilePath'].tolist()
        print("Default mode: Processing only INCLUDED reports for trade extraction.")

    if not all_files_to_process:
        print("No files found to process.")
        return

    print(f"Processing {len(all_files_to_process)} reports for detailed trade data...")
    
    all_sequences = []
    
    # Refresh directory: Delete if exists, then recreate
    trades_out_dir = os.path.join(output_dir, "Trades")
    if os.path.exists(trades_out_dir):
        print(f"Refreshing directory: {trades_out_dir}")
        shutil.rmtree(trades_out_dir)
    os.makedirs(trades_out_dir, exist_ok=True)

    total_files = len(all_files_to_process)
    for i, f in enumerate(all_files_to_process, 1):
        print(f"[{i}/{total_files}] Processing {os.path.basename(f)}...")
        seqs, full_df = parse_sequences_and_deals(f)
        
        # Only add sequences to the portfolio pool if marked for inclusion
        if f in included_files_set:
            all_sequences.extend(seqs)
        
        # Save all trades from this file even if empty
        filename_no_ext = os.path.splitext(os.path.basename(f))[0]
        all_trades_csv = os.path.join(trades_out_dir, f"all_trades_{filename_no_ext}.csv")
        
        if full_df:
            df_full = pd.DataFrame(full_df)
            if 'SourceFile' in df_full.columns:
                df_full.drop(columns=['SourceFile'], inplace=True)
            df_full.to_csv(all_trades_csv, index=False)
        else:
            # Create an empty CSV with headers for consistency
            cols = ['Time', 'Deal', 'Symbol', 'Type', 'Direction', 'Volume', 'Price', 'Order', 'Commission', 'Swap', 'Profit', 'Balance', 'Comment', 'SequenceNumber', 'TradeNumberInSequence']
            pd.DataFrame(columns=cols).to_csv(all_trades_csv, index=False)
            
    # Group by Symbol
    sequences_by_symbol = {}
    for s in all_sequences:
        sym = s['symbol']
        if sym not in sequences_by_symbol:
            sequences_by_symbol[sym] = []
        sequences_by_symbol[sym].append(s)
        
    # Apply non-overlapping logic per symbol
    
    total_trades = 0
    for sym, seqs in sequences_by_symbol.items():
        seqs.sort(key=lambda x: x['start'])
        last_end_time_long = pd.Timestamp.min
        last_end_time_short = pd.Timestamp.min
        
        selected_seq_deals = []
        
        for s in seqs:
            side = s.get('side', 'long')
            if side == 'long':
                if s['start'] > last_end_time_long:
                    selected_seq_deals.extend(s['deals'])
                    last_end_time_long = s['end']
                    total_trades += 1
            else: # short
                if s['start'] > last_end_time_short:
                    selected_seq_deals.extend(s['deals'])
                    last_end_time_short = s['end']
                    total_trades += 1

        if selected_seq_deals:
            # Re-sort all deals in selected sequences by Time for balance calculation
            selected_seq_deals.sort(key=lambda x: pd.to_datetime(x['Time']))
            
            accepted_deals = []
            current_balance = args.base
            
            for d in selected_seq_deals:
                direction = str(d.get('Direction', '')).strip().lower()
                
                if direction == 'in':
                    d['Balance'] = current_balance
                else:
                    # Exit (out or in/out): Balance is updated by net profit (Profit + Commission + Swap)
                    net_pnl = float(d.get('Profit', 0.0)) + float(d.get('Commission', 0.0)) + float(d.get('Swap', 0.0))
                    current_balance += net_pnl
                    d['Balance'] = current_balance
                
                accepted_deals.append(d)

        if accepted_deals:
            out_csv = os.path.join(trades_out_dir, f"selected_trades_{sym}.csv")
            df_selected = pd.DataFrame(accepted_deals)
            
            # Remove SequenceNumber as requested
            if 'SequenceNumber' in df_selected.columns:
                df_selected.drop(columns=['SequenceNumber'], inplace=True)
                
            df_selected.to_csv(out_csv, index=False)

    print(f"Extracted {total_trades} non-overlapping trades.")
    print(f"Deals saved to: {trades_out_dir}")

if __name__ == "__main__":
    main()

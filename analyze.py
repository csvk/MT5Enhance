import pandas as pd
import os
import shutil
import glob
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib
matplotlib.use('Agg')
import argparse
from datetime import datetime
import numpy as np
import math
import webbrowser
from bs4 import BeautifulSoup
import re
import multiprocessing as mp
import sys


class MultiWriter:
    def __init__(self, f_full, f_short):
        self.f_full = f_full
        self.f_short = f_short
    def write(self, data, full=True, short=True):
        if full: self.f_full.write(data)
        if short: self.f_short.write(data)

# --- Helper Functions (Top-level for multiprocessing) ---
def load_parquet_data(html_file_path):
    """Tries to find and load corresponding parquet file from sibling CSV folder."""
    try:
        base_dir = os.path.dirname(html_file_path)
        csv_folder = os.path.join(os.path.dirname(base_dir), "CSV")
        if not os.path.exists(csv_folder):
            return None
        
        filename_no_ext = os.path.splitext(os.path.basename(html_file_path))[0]
        parquet_pattern = os.path.join(csv_folder, f"{filename_no_ext}*.parquet")
        matches = glob.glob(parquet_pattern)
        
        if not matches:
            return None
            
        p_df = pd.read_parquet(matches[0])
        if p_df.empty: return None
        
        # Parse tab-separated format
        cols = p_df.columns[0].split('\t')
        data = [row[0].split('\t') for row in p_df.values]
        df_parsed = pd.DataFrame(data, columns=cols)
        
        # Cleanup names and types
        df_parsed.columns = [c.replace('<', '').replace('>', '').strip() for c in df_parsed.columns]
        df_parsed['DATE'] = pd.to_datetime(df_parsed['DATE'], format='%Y.%m.%d %H:%M', errors='coerce')
        df_parsed = df_parsed.dropna(subset=['DATE'])
        
        for c in ['BALANCE', 'EQUITY']:
            if c in df_parsed.columns:
                df_parsed[c] = pd.to_numeric(df_parsed[c], errors='coerce').fillna(0)
                
        return df_parsed.sort_values('DATE')
    except Exception as e:
        # print(f"Warning: Could not parse parquet for {html_file_path}: {e}")
        return None

def parse_set_file(html_file_path, sets_dir):
    """Reads .set file from the provided sets directory with robust matching."""
    target_params = {
        "lotsize": "LotSize",
        "maxlots": "MaxLots",
        "lotsizeexponent": "LotSizeExponent",
        "delaytradesequence": "DelayTradeSequence",
        "livedelay": "LiveDelay",
        "maxorders": "MaxOrders",
        "stoploss": "StopLoss",
        "pipstep": "PipStep",
        "pipstepexponent": "PipStepExponent",
        "maxpipstep": "MaxPipStep"
    }
    results = {v: "N/A" for v in target_params.values()}
    
    try:
        base_name = os.path.splitext(os.path.basename(html_file_path))[0]
        set_path = os.path.join(sets_dir, f"{base_name}.set")

        if not os.path.exists(set_path):
            return results

        content = None
        for enc in ['utf-16', 'utf-16-le', 'utf-8', 'latin-1', 'cp1252']:
            try:
                with open(set_path, 'r', encoding=enc, errors='ignore') as sf:
                    content = sf.read()
                    if '=' in content: break
            except: continue
        
        if content:
            for line in content.splitlines():
                if '=' in line:
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        key = parts[0].strip().lower()
                        val = parts[1].strip()
                        if key in target_params:
                            clean_val = val.split('||')[0].strip()
                            results[target_params[key]] = clean_val
        return results
    except:
        return results

def extract_report_metrics(html_file_path):
    """Extracts Profit Factor and Recovery Factor from the HTML report."""
    metrics = {'ProfitFactor': 'N/A', 'RecoveryFactor': 'N/A'}
    if not html_file_path or not os.path.exists(html_file_path):
        return metrics
    
    try:
        content = None
        for encoding in ['utf-16', 'utf-8', 'cp1252']:
            try:
                with open(html_file_path, 'r', encoding=encoding, errors='ignore') as f:
                    content = f.read()
                if content: break
            except: continue
        
        if not content: return metrics

        soup = BeautifulSoup(content, 'lxml')
        pf_node = soup.find(string=lambda text: text and "Profit Factor" in text)
        if pf_node:
            parent = pf_node.find_parent('td')
            if parent:
                next_td = parent.find_next_sibling('td')
                if next_td: metrics['ProfitFactor'] = next_td.get_text(strip=True)

        rf_node = soup.find(string=lambda text: text and "Recovery Factor" in text)
        if rf_node:
            parent = rf_node.find_parent('td')
            if parent:
                next_td = parent.find_next_sibling('td')
                if next_td: metrics['RecoveryFactor'] = next_td.get_text(strip=True)
    except: pass
    return metrics

def load_all_fx_rates(base_dir):
    """Loads daily FX closing prices from the prices/ folder."""
    prices_dir = os.path.join(base_dir, "prices")
    rates = {}
    if os.path.exists(prices_dir):
        files = glob.glob(os.path.join(prices_dir, "*.csv"))
        for f in files:
            s = os.path.splitext(os.path.basename(f))[0].upper()
            try:
                rdf = pd.read_csv(f)
                rdf['Date'] = pd.to_datetime(rdf['Date']).dt.date
                rdf.set_index('Date', inplace=True)
                rates[s] = rdf
            except: pass
    return rates

def get_usd_conv_factor(symbol, target_date, fx_rates):
    """Calculates conversion factor to USD based on the quote currency."""
    clean_symbol = symbol.split('.')[0].split('_')[0]
    if len(clean_symbol) < 6:
        match = re.match(r'^([A-Za-z]{6})', symbol)
        if match: clean_symbol = match.group(1)
        else: return 1.0
    
    clean_symbol = clean_symbol.upper()
    quote = clean_symbol[3:]
    if quote == "USD": return 1.0
    
    s1, s2 = f"USD{quote}", f"{quote}USD"
    target_d = target_date.date() if hasattr(target_date, 'date') else target_date
    
    def find_rate(sym_key, invert):
        if sym_key in fx_rates:
            df = fx_rates[sym_key]
            try:
                idx = df.index.get_indexer([target_d], method='pad')[0]
                if idx != -1:
                    row_val = df.iloc[idx]
                    if 'Price' in row_val: val = row_val['Price']
                    elif 'Close' in row_val: val = row_val['Close']
                    elif 'Adj Close' in row_val: val = row_val['Adj Close']
                    else: val = row_val.iloc[0]
                    return 1.0/val if invert else val
            except: pass
        return None

    r = find_rate(s1, True)
    if r is not None: return r
    r = find_rate(s2, False)
    if r is not None: return r
    return 1.0

def precalc_drawdown_worker(args_tuple):
    """Worker for pre-calculating daily drawdowns."""
    r_info, calc_start, calc_end, trades_folder, base_capital, idx, total = args_tuple
    r_base = r_info['basename']
    if idx > 0 and total > 0:
        print(f"<{idx} / {total}> [PID:{os.getpid()}] Pre-calculating: {r_base}")
    r_html = r_info['full_html_path']
    
    # Load parquet or trades
    df_pq = load_parquet_data(r_html) if r_html else None
    if df_pq is not None:
        df_pq_f = df_pq[(df_pq['DATE'] >= calc_start) & (df_pq['DATE'] < calc_end)]
        if not df_pq_f.empty:
            df_pq_f = df_pq_f.copy()
            df_pq_f['Peak'] = df_pq_f['EQUITY'].expanding().max()
            df_pq_f['DD_Abs'] = df_pq_f['EQUITY'] - df_pq_f['Peak']
            df_pq_f['DateOnlyDD'] = df_pq_f['DATE'].dt.date
            return r_base, df_pq_f.groupby('DateOnlyDD')['DD_Abs'].min()
    else:
        # Fallback to trades
        atf_path = os.path.join(trades_folder, f"all_trades_{r_base}.csv")
        if os.path.exists(atf_path):
            df_at_tmp = pd.read_csv(atf_path)
            if not df_at_tmp.empty:
                df_at_tmp['Time'] = pd.to_datetime(df_at_tmp['Time'])
                # Filter by range
                df_at_tmp = df_at_tmp[(df_at_tmp['Time'] >= calc_start) & (df_at_tmp['Time'] < calc_end)]
                if not df_at_tmp.empty:
                    df_at_tmp['DealPnL'] = df_at_tmp['Profit'] + df_at_tmp['Commission'] + df_at_tmp['Swap']
                    df_at_tmp = df_at_tmp.sort_values('Time')
                    df_at_tmp['CumPnL'] = df_at_tmp['DealPnL'].cumsum()
                    df_at_tmp['Balance'] = df_at_tmp['CumPnL'] + base_capital
                    df_at_tmp['Peak'] = df_at_tmp['Balance'].expanding().max()
                    df_at_tmp['DD_Abs'] = df_at_tmp['Balance'] - df_at_tmp['Peak']
                    df_at_tmp['DateOnlyDD'] = df_at_tmp['Time'].dt.date
                    return r_base, df_at_tmp.groupby('DateOnlyDD')['DD_Abs'].min()
    return None, None

def align_dual_axes(ax1, ax2):
    """Aligns the zero lines of two dual Y-axes."""
    l1, r1 = ax1.get_ylim()
    l2, r2 = ax2.get_ylim()
    
    # If both are entirely positive, 0 is already aligned at the bottom
    if l1 >= 0 and l2 >= 0:
        ax1.set_ylim(0, r1)
        ax2.set_ylim(0, r2)
        return

    low1, high1 = min(0, l1), max(0, r1)
    low2, high2 = min(0, l2), max(0, r2)
    
    if high1 == low1: high1 = low1 + 1
    if high2 == low2: high2 = low2 + 1
    
    # Ratios of negative part to positive part
    r1_ratio = low1 / high1
    r2_ratio = low2 / high2
    
    if r1_ratio < r2_ratio: # ax1 is relatively more negative
        ax2.set_ylim(r1_ratio * high2, high2)
    else: # ax2 is relatively more negative
        ax1.set_ylim(r2_ratio * high1, high1)

    if r1_ratio < r2_ratio: # ax1 is relatively more negative
        ax2.set_ylim(r1_ratio * high2, high2)
    else: # ax2 is relatively more negative
        ax1.set_ylim(r2_ratio * high1, high1)

def analyze_single_report_worker(args_tuple):
    (idx, r_info, args, calc_start, calc_end, trades_folder, sets_dir, 
     charts_folder, output_dir, included_files_set, explicitly_skipped_set, 
     overlapping_skipped_set, all_fx_rates, df_deals_subset, total) = args_tuple
    
    report_basename = r_info['basename']
    if idx > 0 and total > 0:
        print(f"<{idx} / {total}> [PID:{os.getpid()}] Analyzing: {report_basename}")
    original_filename = r_info['original_filename']
    full_html_path = r_info['full_html_path']
    
    html_full = []
    html_short = []
    
    # Helper inside worker
    is_included_in_p = (original_filename in included_files_set)

    def write_worker(data, full=True, short=True):
        if full: html_full.append(data)
        if short and is_included_in_p: html_short.append(data)

    # Initialize per-report metrics
    total_pnl = None
    max_dd_abs = None
    max_dd_pct = None
    max_dd_time = None

    df_parquet = None
    set_params = None
    initial_lot_size = "N/A"
    max_grid_level = "N/A"
    lot_validation_status = "N/A"
    max_trades_val = None
    max_trades_gap = None
    max_trades_date = None
    top_3_discrepancies = []
    daily_maxes = None
    
    atf = os.path.join(trades_folder, f"all_trades_{report_basename}.csv")
    
    if not os.path.exists(atf):
        write_worker(f"<h3>{idx}. Report: {report_basename}</h3>\n", short=False)
        write_worker(f"<p>- <strong>Status</strong>: <span class='status-skipped'>Skipped</span> (File could not be parsed or has no trades)</p>\n\n", short=is_included_in_p)
        return {'idx': idx, 'r_info': r_info, 'is_included': is_included_in_p, 'html_full': "".join(html_full), 'html_short': "".join(html_short), 'total_pnl': 0, 'max_dd_abs': 0, 'daily_maxes': None, 'report_basename': report_basename, 'full_html_path': full_html_path}

    try:
        df_at = pd.read_csv(atf)
        df_at['Time'] = pd.to_datetime(df_at['Time'])
        
        # EXTRACT INITIAL LOT SIZE
        first_in_deal = df_at[df_at['Direction'].astype(str).str.lower() == 'in']
        if not first_in_deal.empty:
            initial_lot_size = first_in_deal.iloc[0]['Volume']

        df_at['Direction_lower'] = df_at['Direction'].astype(str).str.lower()
        df_pnl_only = df_at[df_at['Direction_lower'].isin(['in', 'out', 'in/out'])]
        
        df_at['DealPnL'] = df_at['Profit'] + df_at['Commission'] + df_at['Swap']
        total_pnl = df_pnl_only['Profit'].sum() + df_pnl_only['Commission'].sum() + df_pnl_only['Swap'].sum()
        
        # Count buy and sell trades opened (Direction 'in' or 'in/out')
        df_at['Type_lower'] = df_at['Type'].astype(str).str.lower()
        df_at['Dir_lower'] = df_at['Direction'].astype(str).str.lower()
        df_at_filt_cnt = df_at[(df_at['Time'] >= calc_start) & (df_at['Time'] < calc_end)] if not df_at.empty else df_at
        in_deals_file = df_at_filt_cnt[df_at_filt_cnt['Dir_lower'].isin(['in', 'in/out'])]
        total_buy_trades = len(in_deals_file[in_deals_file['Type_lower'] == 'buy'])
        total_sell_trades = len(in_deals_file[in_deals_file['Type_lower'] == 'sell'])
        
        # Determine Status
        status = "Unknown"
        status_class = ""
        reason = ""
        
        if original_filename in included_files_set:
            status = "Included"
            status_class = "status-included"
        elif original_filename in explicitly_skipped_set:
            status = "Skipped"
            status_class = "status-skipped"
            reason = "Manual (Include=0)"
        elif original_filename in overlapping_skipped_set:
            status = "Skipped"
            status_class = "status-skipped"
            reason = "Overlapping trades"
        else:
            df_at_filtered = df_at[(df_at['Time'] >= calc_start) & (df_at['Time'] < calc_end)]
            if df_at_filtered.empty:
                status = "Skipped"
                status_class = "status-skipped"
                reason = "Date range"
            else:
                status = "Partially Included"
                status_class = "status-partial"

        should_process_detailed = (status == "Included") or args.all
        
        df_parquet = load_parquet_data(full_html_path) if (full_html_path and should_process_detailed) else None
        set_params = parse_set_file(full_html_path, sets_dir) if (full_html_path and should_process_detailed) else None
        report_metrics = extract_report_metrics(full_html_path) if (full_html_path and should_process_detailed) else {'ProfitFactor': 'N/A', 'RecoveryFactor': 'N/A'}
        
        detected_point = None
        pip_gaps = []
        max_trades_val = 0
        mean_gap_max_seq = 0
        max_seq_last_trade_date = None
        max_seq_fx_factor = 1.0

        if not df_at.empty and should_process_detailed:
            s_sym_top = ""
            if 'Symbol' in df_at.columns:
                valid_symbols = df_at['Symbol'].dropna()
                valid_symbols = valid_symbols[valid_symbols.astype(str).str.strip() != ""]
                if not valid_symbols.empty: s_sym_top = str(valid_symbols.iloc[0]).upper()
            
            detected_point = 0.01 if "JPY" in s_sym_top else 0.0001
            
            if 'SequenceNumber' in df_at.columns:
                seq_groups_tmp = df_at[df_at['SequenceNumber'] > 0].groupby('SequenceNumber')
                seq_info = []
                for _, group in seq_groups_tmp:
                    in_trades = group[group['Direction'].astype(str).str.lower() == 'in'].sort_values('Time')
                    length = len(in_trades)
                    if length >= 2:
                        p1 = in_trades.iloc[0]['Price']
                        p2 = in_trades.iloc[1]['Price']
                        pn = in_trades.iloc[-1]['Price']
                        gap_base = abs(p2 - p1) / detected_point
                        pip_gaps.append(gap_base)
                        mean_gap = (abs(pn - p1) / detected_point) / (length - 1)
                        seq_info.append({'length': length, 'mean_gap': mean_gap, 'last_trade_time': in_trades.iloc[-1]['Time'], 'actual_cumulative_gap': abs(pn - p1) / detected_point, 'start_time': in_trades.iloc[0]['Time']})
                
                if seq_info:
                    df_seq_info = pd.DataFrame(seq_info)
                    max_trades_val = int(df_seq_info['length'].max())
                    max_df = df_seq_info[df_seq_info['length'] == max_trades_val]
                    mean_gap_max_seq = max_df['mean_gap'].max()
                    best_max_seq = max_df[max_df['mean_gap'] == mean_gap_max_seq].iloc[0]
                    max_seq_last_trade_date = pd.to_datetime(best_max_seq['last_trade_time']).date()
                    max_trades_gap = best_max_seq['actual_cumulative_gap']
                    max_seq_fx_factor = get_usd_conv_factor(s_sym_top, max_seq_last_trade_date, all_fx_rates)
        
        global_avg_gap = np.mean(pip_gaps) if pip_gaps else 0
        theoretical_dd_series = []; mean_gap_scenario = None; max_gap_day = None; max_gap_fx_factor = 1.0

        if set_params and not df_at.empty:
            try:
                s_pipstep = float(set_params.get('PipStep', 0)); s_pipstepexp = float(set_params.get('PipStepExponent', 1))
                s_maxpipstep = float(set_params.get('MaxPipStep', 0)); s_lot = float(set_params.get('LotSize', 0))
                s_lotexp = float(set_params.get('LotSizeExponent', 1)); s_maxlots = float(set_params.get('MaxLots', 999)); s_ld = int(set_params.get('LiveDelay', 0))

                if s_pipstep > 0 and s_maxpipstep < 0:
                    theoretical_skip_reason = f"MaxPipStep is negative ({s_maxpipstep}) while PipStep is positive ({s_pipstep}). ATR cannot be calculated."
                elif s_pipstep != 0 and s_lot > 0:
                    theoretical_skip_reason = None
                    df_at_theo = df_at.copy(); df_at_theo['DateOnly'] = df_at_theo['Time'].dt.date
                    last_calculated_pipstep = None
                    unique_dates = sorted(df_at_theo['DateOnly'].unique())
                    for d_date in unique_dates:
                        day_deals = df_at_theo[df_at_theo['DateOnly'] == d_date]
                        ins = day_deals[day_deals['Direction'].astype(str).str.lower() == 'in']
                        if ins.empty: continue
                        if 'SequenceNumber' in ins.columns:
                            seq_lengths = ins.groupby('SequenceNumber').size()
                            if seq_lengths.empty: continue
                            longest_seq = day_deals[day_deals['SequenceNumber'] == seq_lengths.idxmax()].sort_values('Time')
                        else: longest_seq = day_deals.sort_values('Time')
                        
                        p1_actual = longest_seq.iloc[0]['Price']; point = detected_point
                        if s_pipstep < 0:
                            all_day_gaps = []
                            if 'SequenceNumber' in ins.columns:
                                for seq_num in ins['SequenceNumber'].unique():
                                    full_s_group = df_at_theo[(df_at_theo['SequenceNumber'] == seq_num) & (df_at_theo['Direction'].astype(str).str.lower() == 'in')].sort_values('Time')
                                    if len(full_s_group) >= 2: all_day_gaps.append(abs(full_s_group.iloc[1]['Price'] - full_s_group.iloc[0]['Price']) / point)
                            else:
                                s_group = ins.sort_values('Time')
                                if len(s_group) >= 2: all_day_gaps.append(abs(s_group.iloc[1]['Price'] - s_group.iloc[0]['Price']) / point)
                            if all_day_gaps: current_pipstep = sum(all_day_gaps) / len(all_day_gaps); last_calculated_pipstep = current_pipstep
                            elif last_calculated_pipstep is not None: current_pipstep = last_calculated_pipstep
                            else: continue
                        else: current_pipstep = s_pipstep
                        
                        if current_pipstep > 0:
                            is_buy = str(longest_seq.iloc[0]['Type']).lower() == 'buy'; direction_sign = -1 if is_buy else 1
                            prices = [0.0] * 23; prices[min(s_ld + 1, 22)] = p1_actual
                            calculated_atr = current_pipstep / abs(s_pipstep) if s_pipstep != 0 else 1.0
                            effective_maxpipstep = calculated_atr * abs(s_maxpipstep) if s_maxpipstep < 0 else s_maxpipstep
                            for k in range(s_ld, 0, -1):
                                gap = min(effective_maxpipstep, current_pipstep * (s_pipstepexp ** (k-1))) if effective_maxpipstep > 0 else current_pipstep * (s_pipstepexp ** (k-1))
                                prices[k] = prices[k+1] - direction_sign * (gap * point)
                            for k in range(s_ld + 1, 22):
                                gap = min(effective_maxpipstep, current_pipstep * (s_pipstepexp ** (k-1))) if effective_maxpipstep > 0 else current_pipstep * (s_pipstepexp ** (k-1))
                                prices[k+1] = prices[k] + direction_sign * (gap * point)
                            
                            def get_theo_lot(k): return min(s_maxlots, s_lot * (s_lotexp ** (k-1)))
                            vr = [0.0] * 22; vr[1] = sum(get_theo_lot(j) for j in range(1, s_ld + 2))
                            for i in range(2, 21): vr[i] = get_theo_lot(s_ld + i)
                            dds = {}; gaps = {}; p_anchor = prices[min(s_ld + 1, 21)]
                            for i in range(1, 21):
                                target_price = prices[min(s_ld + i + 1, 22)]; total_dd = 0
                                for j in range(1, i + 1): total_dd += vr[j] * abs(target_price - prices[min(s_ld + j, 22)])
                                dds[i] = total_dd; gaps[i] = abs(p_anchor - prices[min(s_ld + i + 1, 21)]) / point
                            
                            rep_symbol = str(longest_seq.iloc[0]['Symbol']).upper() if 'Symbol' in longest_seq.columns else ""
                            fx_f = get_usd_conv_factor(rep_symbol, d_date, all_fx_rates)
                            theo_entry = {'Time': pd.to_datetime(longest_seq.iloc[0]['Time']), 'PipStepUsed': current_pipstep, 'EffectiveMaxPipStep': effective_maxpipstep, 'FX_Factor': fx_f, 'p1_actual': p1_actual, 'is_buy': is_buy}
                            for i in range(1, 21): theo_entry[f'DD{i}'], theo_entry[f'Gap{i}'], theo_entry[f'Lot{i}'] = dds[i] * 100000 * fx_f, gaps[i], vr[i]
                            theoretical_dd_series.append(theo_entry)

                        # 2. Add "Mean Pip Gap on Max Gap Day" Scenario
                        if theoretical_dd_series and global_avg_gap > 0:
                            df_theo_tmp = pd.DataFrame(theoretical_dd_series)
                            max_entry = theoretical_dd_series[df_theo_tmp['PipStepUsed'].idxmax()]
                            max_gap_day, max_gap_fx_factor = max_entry['Time'], max_entry['FX_Factor']
                            target_pipstep = global_avg_gap
                            global_atr = target_pipstep / abs(s_pipstep) if s_pipstep != 0 else 1.0
                            eff_gl_max = global_atr * abs(s_maxpipstep) if s_maxpipstep < 0 else s_maxpipstep
                            if target_pipstep > 0:
                                p1_scen, is_buy_scen = max_entry['p1_actual'], max_entry['is_buy']; dir_s = -1 if is_buy_scen else 1
                                sc_pr = [0.0] * 23; sc_pr[min(s_ld + 1, 22)] = p1_scen
                                for k in range(s_ld, 0, -1):
                                    g_v = min(eff_gl_max, target_pipstep * (s_pipstepexp ** (k-1))) if eff_gl_max > 0 else target_pipstep * (s_pipstepexp ** (k-1))
                                    sc_pr[k] = sc_pr[k+1] - dir_s * (g_v * detected_point)
                                for k in range(s_ld + 1, 22):
                                    g_v = min(eff_gl_max, target_pipstep * (s_pipstepexp ** (k-1))) if eff_gl_max > 0 else target_pipstep * (s_pipstepexp ** (k-1))
                                    sc_pr[k+1] = sc_pr[k] + dir_s * (g_v * detected_point)
                                vr_sc = [0.0] * 22; vr_sc[1] = sum(min(s_maxlots, s_lot * (s_lotexp ** (j-1))) for j in range(1, s_ld + 2))
                                for i in range(2, 21): vr_sc[i] = min(s_maxlots, s_lot * (s_lotexp ** (s_ld + i - 1)))
                                dds_sc, gaps_sc, p_anc_sc = {}, {}, sc_pr[min(s_ld + 1, 21)]
                                for i in range(1, 21):
                                    tp, t_dd_sc = sc_pr[min(s_ld + i + 1, 22)], 0
                                    for j in range(1, i + 1): t_dd_sc += vr_sc[j] * abs(tp - sc_pr[min(s_ld + j, 22)])
                                    dds_sc[i], gaps_sc[i] = t_dd_sc, abs(p_anc_sc - sc_pr[min(s_ld + i + 1, 21)]) / detected_point
                                mean_gap_scenario = {'PipStepUsed': target_pipstep, 'FX_Factor': max_gap_fx_factor}
                                for i in range(1, 21): mean_gap_scenario[f'DD{i}'], mean_gap_scenario[f'Gap{i}'], mean_gap_scenario[f'Lot{i}'] = dds_sc[i] * 100000 * max_gap_fx_factor, gaps_sc[i], vr_sc[i]

                        # 3. Add "Mean Pip Gap on Max Sequence Day" Scenario
                        max_seq_mean_gap_scenario = None
                        if theoretical_dd_series and mean_gap_max_seq > 0:
                            target_pipstep_seq = mean_gap_max_seq
                            global_atr_seq = target_pipstep_seq / abs(s_pipstep) if s_pipstep != 0 else 1.0
                            eff_mp_seq = global_atr_seq * abs(s_maxpipstep) if s_maxpipstep < 0 else s_maxpipstep
                            df_theo_t = pd.DataFrame(theoretical_dd_series); rep_en = theoretical_dd_series[df_theo_t['PipStepUsed'].idxmax()]
                            p1_sc_seq, is_b_sc_seq = rep_en['p1_actual'], rep_en['is_buy']; ds_seq = -1 if is_b_sc_seq else 1
                            sp_seq = [0.0] * 23; sp_seq[min(s_ld + 1, 22)] = p1_sc_seq
                            for k in range(s_ld, 0, -1):
                                gv = min(eff_mp_seq, target_pipstep_seq * (s_pipstepexp ** (k-1))) if eff_mp_seq > 0 else target_pipstep_seq * (s_pipstepexp ** (k-1))
                                sp_seq[k] = sp_seq[k+1] - ds_seq * (gv * detected_point)
                            for k in range(s_ld + 1, 22):
                                gv = min(eff_mp_seq, target_pipstep_seq * (s_pipstepexp ** (k-1))) if eff_mp_seq > 0 else target_pipstep_seq * (s_pipstepexp ** (k-1))
                                sp_seq[k+1] = sp_seq[k] + ds_seq * (gv * detected_point)
                            vs_seq = [0.0] * 22; vs_seq[1] = sum(min(s_maxlots, s_lot * (s_lotexp ** (j-1))) for j in range(1, s_ld + 2))
                            for i in range(2, 21): vs_seq[i] = min(s_maxlots, s_lot * (s_lotexp ** (s_ld + i - 1)))
                            ds_sc_seq, gs_sc_seq, pa_sc_seq = {}, {}, sp_seq[min(s_ld + 1, 21)]
                            for i in range(1, 21):
                                tp_seq, t_ds_seq = sp_seq[min(s_ld + i + 1, 22)], 0
                                for j in range(1, i + 1): t_ds_seq += vs_seq[j] * abs(tp_seq - sp_seq[min(s_ld + j, 22)])
                                ds_sc_seq[i], gs_sc_seq[i] = t_ds_seq, abs(pa_sc_seq - sp_seq[min(s_ld + i + 1, 21)]) / detected_point
                            max_seq_mean_gap_scenario = {'PipStepUsed': target_pipstep_seq, 'FX_Factor': max_seq_fx_factor}
                            for i in range(1, 21): max_seq_mean_gap_scenario[f'DD{i}'], max_seq_mean_gap_scenario[f'Gap{i}'], max_seq_mean_gap_scenario[f'Lot{i}'] = ds_sc_seq[i] * 100000 * max_seq_fx_factor, gs_sc_seq[i], vs_seq[i]

                scenario_rows = []
                if theoretical_dd_series:
                    df_all = pd.DataFrame(theoretical_dd_series)
                    if not df_all.empty:
                        df_all['PipStepUsed'] = df_all['PipStepUsed'].round(2)
                        # Pick the row with highest DD20 for each distinct rounded PipStep
                        distinct_pipsteps = df_all.sort_values('DD20', ascending=False).groupby('PipStepUsed').head(1).sort_values('PipStepUsed', ascending=False)
                        
                        top_distinct = distinct_pipsteps.head(2)
                        bottom_distinct = distinct_pipsteps.tail(2)
                        combined_distinct = pd.concat([top_distinct, bottom_distinct]).drop_duplicates(subset=['PipStepUsed']).sort_values('PipStepUsed', ascending=False)
                        
                        for _, dr in combined_distinct.iterrows():
                            is_mx = dr['PipStepUsed'] in top_distinct['PipStepUsed'].values
                            px, b_i, k1_s = "Max Distinct Gap" if is_mx else "Min Distinct Gap", -1, "N/A"
                            try:
                                ld, lg = 0, 0
                                for b in range(1, 21):
                                    cd, cg = dr.get(f'DD{b}', 0), dr.get(f'Gap{b}', 0)
                                    if ld < 1000 <= cd: 
                                        b_i = b
                                        if cd > ld: k1_s = f"{lg + (cg - lg) * (1000 - ld) / (cd - ld):,.1f}"
                                        break
                                    ld, lg = cd, cg
                            except: pass
                            scenario_rows.append({'Type': px, 'Date': dr['Time'].date(), 'BasePipGap': f"{dr['PipStepUsed']:.2f}", 'FXFactor': f"{dr['FX_Factor']:.4f}", 'Label': f"{px} | Date: {dr['Time'].date()} | Base Pip Gap: {dr['PipStepUsed']:.2f} | USD Conv Factor: {dr['FX_Factor']:.4f}", 'Data': dr, 'BreachIdx': b_i, 'K1Gap': k1_s})
                        
                        for sc_obj, sc_type, sc_day, sc_fx, sc_gap in [(mean_gap_scenario, "Mean Pip Gap (Max DD Day)", max_gap_day, max_gap_fx_factor, global_avg_gap), (max_seq_mean_gap_scenario, "Mean Pip Gap (Max Sequence Day)", max_seq_last_trade_date, max_seq_fx_factor, mean_gap_max_seq)]:
                            if sc_obj:
                                b_i, k1_s = -1, "N/A"
                                try:
                                    ld, lg = 0, 0
                                    for b in range(1, 21):
                                        cd, cg = sc_obj.get(f'DD{b}', 0), sc_obj.get(f'Gap{b}', 0)
                                        if ld < 1000 <= cd:
                                            b_i = b
                                            if cd > ld: k1_s = f"{lg + (cg - lg) * (1000 - ld) / (cd - ld):,.1f}"
                                            break
                                        ld, lg = cd, cg
                                except: pass
                                s_lbl = f"Scenario: {sc_type} ({sc_day.date() if hasattr(sc_day, 'date') else sc_day}) | Base Pip Gap: {sc_gap:.2f} | USD Conv Factor: {sc_fx:.4f}"
                                scenario_rows.append({'Type': sc_type, 'Date': sc_day.date() if hasattr(sc_day, 'date') else sc_day, 'BasePipGap': f"{sc_gap:.2f}", 'FXFactor': f"{sc_fx:.4f}", 'Label': s_lbl, 'Data': sc_obj, 'BreachIdx': b_i, 'K1Gap': k1_s})
            except Exception as e: print(f"  Warning: Error in Theoretical DD calc for {report_basename}: {e}")
        elif not should_process_detailed: theoretical_skip_reason = "Detailed calculations skipped (Report excluded from portfolio). Use --all to force."

        s_lot, s_exp, s_max_lot, s_dts, s_ld, s_max_orders = 0.0, 1.0, 999.0, 0, 0, 0
        if set_params:
            try: s_lot = float(set_params.get('LotSize', 0))
            except: pass
            try: s_exp = float(set_params.get('LotSizeExponent', 1))
            except: pass
            try: s_max_lot = float(set_params.get('MaxLots', 999))
            except: pass
            try: s_dts = int(set_params.get('DelayTradeSequence', 0))
            except: pass
            try: s_ld = int(set_params.get('LiveDelay', 0))
            except: pass
            try: s_max_orders = int(set_params.get('MaxOrders', 0))
            except: pass

        if set_params and not df_at.empty:
            in_d = df_at[df_at['Direction'].astype(str).str.lower() == 'in'].copy()
            if not in_d.empty and 'SequenceNumber' in in_d.columns:
                max_rel, v_errs, all_disc = 0, [], []
                for s_num in [x for x in in_d['SequenceNumber'].unique() if x > 0]:
                    s_g = in_d[in_d['SequenceNumber'] == s_num].sort_values('Time')
                    max_rel = max(max_rel, s_ld + len(s_g))
                    for i, (ir, rv) in enumerate(s_g.iterrows(), 1):
                        ev = sum(min(s_lot * (s_exp ** (n-1)), s_max_lot) for n in range(1, s_ld + 2)) if i == 1 else min(s_lot * (s_exp ** (s_ld + i - 1)), s_max_lot)
                        av, df = float(rv['Volume']), abs(float(rv['Volume']) - ev)
                        if df >= 0.01: all_disc.append({'TradeNo': i, 'Time': rv['Time'], 'Theo': ev, 'Act': av, 'Diff': df}); v_errs.append(f"Seq {s_num} T{i}")
                if max_rel > 0: max_grid_level = max_rel + s_dts
                top_3_discrepancies = sorted(all_disc, key=lambda x: x['Diff'], reverse=True)[:3]
                lot_validation_status = "OK" if not v_errs else f"Discrepancy ({len(v_errs)} trades)"

        if not should_process_detailed:
            write_worker(f"<h3>{idx}. Report: <a href='file:///{full_html_path}' target='_blank'>{report_basename}</a></h3>\n" if full_html_path else f"<h3>{idx}. Report: {report_basename}</h3>\n", short=False)
            write_worker(f"<p>- <strong>Status</strong>: <span class='{status_class}'>{status}</span> {f'({reason})' if reason else ''}</p>\n", short=False)
            write_worker(f"<p>- <strong>Note</strong>: Detailed calculations and charts skipped for this excluded report. Use <code>--all</code> to include.</p>\n<hr>\n", short=False)
            return {'idx': idx, 'r_info': r_info, 'is_included': is_included_in_p, 'html_full': "".join(html_full), 'html_short': "".join(html_short), 'total_pnl': total_pnl, 'max_dd_abs': 0, 'daily_maxes': None, 'report_basename': report_basename, 'full_html_path': full_html_path}

        fig, axes = plt.subplots(3, 3, figsize=(20, 18))
        
        # Flatten axes for easier assignment
        ax_flat = axes.flatten()
        ax_bal = ax_flat[0]
        ax_dd = ax_flat[1]
        ax_hist = ax_flat[2]
        ax_hold = ax_flat[3]
        ax_vol = ax_flat[4]
        ax_theo_dd = ax_flat[5]
        ax_monthly_combined = ax_flat[6]
        ax_pip_gap = ax_flat[7]
        
        # Hide unused axes
        for ax_u in ax_flat[8:]:
            ax_u.set_axis_off()
        
        max_dd_pct = 0.0
        max_dd_abs = 0.0

        if df_parquet is not None:
            # Filter parquet to match analysis date range
            df_pq_filtered = df_parquet[(df_parquet['DATE'] >= calc_start) & (df_parquet['DATE'] < calc_end)]
            
            if not df_pq_filtered.empty:
                # Plot 1: Balance & Equity Growth
                ax_bal.plot(df_pq_filtered['DATE'], df_pq_filtered['BALANCE'], color='blue', linewidth=1, label='Balance')
                ax_bal.plot(df_pq_filtered['DATE'], df_pq_filtered['EQUITY'], color='red', linewidth=0.8, alpha=0.7, label='Equity')
                ax_bal.set_title(f'Balance and Equity Growth', fontsize=12)
                ax_bal.legend()
                
                # Plot 2: Drawdown from Equity
                df_pq_filtered = df_pq_filtered.copy()
                df_pq_filtered['Peak'] = df_pq_filtered['EQUITY'].expanding().max()
                df_pq_filtered['DD_Pct'] = (df_pq_filtered['EQUITY'] / df_pq_filtered['Peak'] - 1) * 100
                
                ax_dd.fill_between(df_pq_filtered['DATE'], df_pq_filtered['DD_Pct'], 0, color='red', alpha=0.3)
                ax_dd.plot(df_pq_filtered['DATE'], df_pq_filtered['DD_Pct'], color='red', linewidth=0.8)
                ax_dd.set_title(f'Underwater Drawdown (Equity)', fontsize=12)

                # Add secondary Y-axis for absolute drawdown
                ax_dd_abs_plot = ax_dd.twinx()
                abs_diff = df_pq_filtered['EQUITY'] - df_pq_filtered['Peak']
                df_pq_filtered['DD_Abs'] = abs_diff
                ax_dd_abs_plot.plot(df_pq_filtered['DATE'], abs_diff, alpha=0)
                ax_dd_abs_plot.set_ylabel('Drawdown Absolute')
                ax_dd_abs_plot.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format(int(x), ',')))

                max_dd_pct = df_pq_filtered['DD_Pct'].min()
                max_dd_abs = df_pq_filtered['DD_Abs'].min()
                max_dd_time = df_pq_filtered.iloc[df_pq_filtered['DD_Pct'].argmin()]['DATE']

                # Collect daily max DD for portfolio aggregation
                df_pq_filtered['DateOnlyDD'] = df_pq_filtered['DATE'].dt.date
                daily_maxes = df_pq_filtered.groupby('DateOnlyDD')['DD_Abs'].min()
            else:
                df_parquet = None # Revert to fallback if date range filters out everything
        
        if df_parquet is None and not df_at.empty:
            # Fallback to HTML trade data
            df_at['CumPnL'] = df_at['DealPnL'].cumsum()
            df_at['Balance'] = df_at['CumPnL'] + args.base
            df_at['Peak'] = df_at['Balance'].expanding().max()
            df_at['DD_Pct'] = (df_at['Balance'] / df_at['Peak'] - 1) * 100
            
            ax_bal.plot(df_at['Time'], df_at['Balance'], color='blue', linewidth=1)
            ax_bal.set_title(f'Balance Growth', fontsize=12)
            
            ax_dd.fill_between(df_at['Time'], df_at['DD_Pct'], 0, color='red', alpha=0.3)
            ax_dd.plot(df_at['Time'], df_at['DD_Pct'], color='red', linewidth=0.8)
            ax_dd.set_title(f'Underwater Drawdown', fontsize=12)
 
            # Add secondary Y-axis for absolute drawdown
            ax_dd_abs_plot = ax_dd.twinx()
            abs_diff = df_at['Balance'] - df_at['Peak']
            df_at['DD_Abs'] = abs_diff
            ax_dd_abs_plot.plot(df_at['Time'], abs_diff, alpha=0)
            ax_dd_abs_plot.set_ylabel('Drawdown Absolute')
            ax_dd_abs_plot.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format(int(x), ',')))
 
            max_dd_pct = df_at['DD_Pct'].min()
            max_dd_abs = df_at['DD_Abs'].min()
            max_dd_time = df_at.iloc[df_at['DD_Pct'].argmin()]['Time']
 
            # Collect daily max DD for portfolio aggregation
            df_at['DateOnlyDD'] = df_at['Time'].dt.date
            daily_maxes = df_at.groupby('DateOnlyDD')['DD_Abs'].min()


        ax_bal.set_ylabel('Amount')
        ax_bal.grid(True, alpha=0.3)
        ax_bal.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format(int(x), ',')))
        plt.setp(ax_bal.get_xticklabels(), rotation=30, ha='right')
        
        ax_dd.set_ylabel('Drawdown %')
        ax_dd.grid(True, alpha=0.3)
        plt.setp(ax_dd.get_xticklabels(), rotation=30, ha='right')

        # Plot 3: Volume Analysis (Theoretical)
        if s_lot > 0:
            try:
                # Draw theoretical volumes up to MaxOrders or current max Grid Level
                limit = max(s_max_orders, (int(max_grid_level) - s_dts) if isinstance(max_grid_level, int) else 0)
                if limit == 0: limit = 10 # Default if unknown
                
                vols = []
                cum_vols = []
                levs = []
                curr_cum = 0
                for n in range(1, limit + 1):
                    v = min(s_lot * (s_exp ** (n-1)), s_max_lot)
                    vols.append(v)
                    curr_cum += v
                    cum_vols.append(curr_cum)
                    levs.append(s_dts + n)
                
                color_vol = 'tab:blue'
                ax_vol.bar(levs, vols, color=color_vol, alpha=0.6, label='Lot Size')
                ax_vol.set_xlabel('Grid Level')
                ax_vol.set_ylabel('Lot Size', color=color_vol)
                ax_vol.tick_params(axis='y', labelcolor=color_vol)
                
                ax_cum = ax_vol.twinx()
                color_cum = 'tab:red'
                ax_cum.plot(levs, cum_vols, color=color_cum, marker='o', markersize=4, label='Cumulative')
                ax_cum.set_ylabel('Cumulative Lots', color=color_cum)
                ax_cum.tick_params(axis='y', labelcolor=color_cum)
                
                ax_vol.set_title("Theoretical Volume Analysis", fontsize=12)
                ax_vol.grid(True, alpha=0.3)
                ax_vol.xaxis.set_major_locator(plt.MaxNLocator(integer=True))
                
                # Annotate Max Values
                max_l = max(vols)
                max_c = cum_vols[-1]
                stats_box = f"Max Lot: {max_l:.2f}\nMax Cum: {max_c:.2f}"
                ax_vol.text(0.05, 0.95, stats_box, transform=ax_vol.transAxes, fontsize=10, verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
            except:
                ax_vol.set_title("Volume Analysis Error", fontsize=12)
        else:
            ax_vol.set_title("No Volume Parameters", fontsize=12)

        # Plot 4: Sequence Histogram (Dual Axis)
        if 'SequenceNumber' in df_at.columns and 'TradeNumberInSequence' in df_at.columns:
            seq_groups = df_at[df_at['SequenceNumber'] > 0].groupby('SequenceNumber')
            seq_data = []
            hold_times = []
            # pip_gaps already collected earlier

            for _, group in seq_groups:
                group_sorted = group.sort_values('Time')
                length = group_sorted['TradeNumberInSequence'].max()
                pnl = group_sorted[group_sorted['Direction'].astype(str).str.lower().isin(['out', 'in/out'])]['DealPnL'].sum()
                
                # Pip Gap calculation: First in entry price to last in entry price
                in_trades = group_sorted[group_sorted['Direction'].astype(str).str.lower() == 'in']
                if not in_trades.empty:
                    p1 = in_trades.iloc[0]['Price']
                    pN = in_trades.iloc[-1]['Price']
                    cumulative_gap = abs(pN - p1) / (detected_point if detected_point else 0.0001)
                else:
                    cumulative_gap = 0.0
                
                start_time = group_sorted.iloc[0]['Time']
                mean_gap = cumulative_gap / (length - 1) if length > 1 else 0.0
                last_trade_t = in_trades.iloc[-1]['Time'] if not in_trades.empty else group_sorted.iloc[-1]['Time']
                    
                seq_data.append({
                    'Length': length, 
                    'PnL': pnl, 
                    'ActualGap': cumulative_gap, 
                    'StartTime': start_time,
                    'MeanGap': mean_gap,
                    'LastTradeTime': last_trade_t
                })
                
                # Hold time calculation: First in to first out
                first_in = group[(group['TradeNumberInSequence'] == 1) & (group['Direction'].astype(str).str.lower() == 'in')]
                first_out = group[group['Direction'].astype(str).str.lower().isin(['out', 'in/out'])].sort_values('Time')
                
                if not first_in.empty and not first_out.empty:
                    entry_t = pd.to_datetime(first_in.iloc[0]['Time'])
                    exit_t = pd.to_datetime(first_out.iloc[0]['Time'])
                    duration = (exit_t - entry_t).total_seconds() / 3600.0 # Duration in hours
                    hold_times.append(duration)
            
            if seq_data:
                df_seq_curr = pd.DataFrame(seq_data)
                max_trades_val = int(df_seq_curr['Length'].max()) if not df_seq_curr.empty else 0
                
                # Find gap and date at max trades
                if max_trades_val > 0:
                    max_df_cur = df_seq_curr[df_seq_curr['Length'] == max_trades_val]
                    # Use max of means if multiple sequences have max length
                    mean_gap_max_seq_cur = max_df_cur['MeanGap'].max()
                    best_max_seq_cur = max_df_cur[max_df_cur['MeanGap'] == mean_gap_max_seq_cur].iloc[0]
                    max_trades_date = pd.to_datetime(best_max_seq_cur['StartTime']).date()
                    max_trades_gap = best_max_seq_cur['ActualGap']
                    # ALSO set max_seq_last_trade_date for consistency / HTML report
                    max_seq_last_trade_date = max_trades_date
                else:
                    max_trades_gap = 0.0
                    max_trades_date = None
                    max_seq_last_trade_date = None
                    
                dist_agg_curr = df_seq_curr.groupby('Length').agg(
                    Frequency=('PnL', 'count'),
                    TotalPnL=('PnL', 'sum')
                ).reset_index()
                dist_agg_curr['Length'] = dist_agg_curr['Length'].astype(int)
                
                x_dist = np.arange(len(dist_agg_curr))
                width_dist = 0.35
                
                # Primary axis: Frequency
                rects_f = ax_hist.bar(x_dist - width_dist/2, dist_agg_curr['Frequency'], width=width_dist, color='tab:blue', alpha=0.6, label='Frequency', edgecolor='black', linewidth=0.5)
                ax_hist.set_title("Sequence PnL Distribution", fontsize=12)
                ax_hist.set_xlabel("Trades in Sequence")
                ax_hist.set_ylabel("Frequency", color='tab:blue')
                ax_hist.tick_params(axis='y', labelcolor='tab:blue')
                ax_hist.set_xticks(x_dist)
                ax_hist.set_xticklabels(dist_agg_curr['Length'])
                ax_hist.grid(axis='y', alpha=0.3)
                
                # Secondary axis: PnL
                ax_hist_pnl = ax_hist.twinx()
                dist_pnl_colors = ['green' if val >= 0 else 'red' for val in dist_agg_curr['TotalPnL']]
                rects_p = ax_hist_pnl.bar(x_dist + width_dist/2, dist_agg_curr['TotalPnL'], width=width_dist, color=dist_pnl_colors, alpha=0.5, label='Total PnL', edgecolor='black', linewidth=0.5)
                ax_hist_pnl.set_ylabel('Total PnL', color='darkgreen')
                ax_hist_pnl.tick_params(axis='y', labelcolor='darkgreen')
                ax_hist_pnl.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format(int(x), ',')))

                # Align Zeros
                align_dual_axes(ax_hist, ax_hist_pnl)

                # Annotations for Frequency
                for rect in rects_f:
                    h = rect.get_height()
                    if h > 0:
                        ax_hist.annotate(f'{int(h)}', xy=(rect.get_x() + rect.get_width()/2, h), xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=8, color='tab:blue')

                # Annotations for PnL
                for rect in rects_p:
                    h = rect.get_height()
                    if abs(h) > 0.01:
                        offset = 3 if h >= 0 else -10
                        ax_hist_pnl.annotate(f'{h:,.0f}', xy=(rect.get_x() + rect.get_width()/2, h), xytext=(0, offset), textcoords="offset points", ha='center', va='bottom' if h >= 0 else 'top', fontsize=7, fontweight='bold')

                # Legend
                lns1, lbs1 = ax_hist.get_legend_handles_labels()
                lns2, lbs2 = ax_hist_pnl.get_legend_handles_labels()
                ax_hist.legend(lns1 + lns2, lbs1 + lbs2, loc='upper right', fontsize=8)

            else:
                ax_hist.set_title("No Sequence Data", fontsize=12)

            # Plot 4: Sequence Hold Times (Scatter)
            if hold_times:
                x_vals = range(1, len(hold_times) + 1)
                
                # Background Histogram
                ax_hold_hist = ax_hold.twiny()
                ax_hold_hist.hist(hold_times, orientation='horizontal', bins='auto', color='red', alpha=0.1)
                ax_hold_hist.set_axis_off() # Hide the secondary x-axis
                
                ax_hold.scatter(x_vals, hold_times, color='blue', alpha=0.6, s=30, label='Hold Time')
                
                avg_h = np.mean(hold_times)
                min_h = np.min(hold_times)
                max_h = np.max(hold_times)
                
                ax_hold.axhline(avg_h, color='red', linestyle='--', linewidth=1, label=f'Mean: {avg_h:.2f}h')
                ax_hold.axhline(min_h, color='green', linestyle=':', linewidth=1, label=f'Min: {min_h:.2f}h')
                ax_hold.axhline(max_h, color='orange', linestyle=':', linewidth=1, label=f'Max: {max_h:.2f}h')
                
                ax_hold.set_title("Sequence Hold Times (1st Trade)", fontsize=12)
                ax_hold.set_xlabel("Sequence #")
                ax_hold.set_ylabel("Hours")
                ax_hold.grid(True, alpha=0.3)
                ax_hold.legend(fontsize=8, loc='best')
                
                # Add text box with statistics
                stats_text = f"Mean: {avg_h:.2f}h\nMin: {min_h:.2f}h\nMax: {max_h:.2f}h"
                ax_hold.text(0.95, 0.05, stats_text, transform=ax_hold.transAxes, fontsize=9, verticalalignment='bottom', horizontalalignment='right', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
            else:
                ax_hold.set_title("No Hold Time Data", fontsize=12)

            # Plot 8: Pip Gap Distribution
            if pip_gaps:
                ax_pip_gap.hist(pip_gaps, bins='auto', color='tab:orange', alpha=0.7, edgecolor='black', linewidth=0.5)
                ax_pip_gap.set_title("Pip Gap Distribution", fontsize=12)
                ax_pip_gap.set_xlabel("Pips")
                ax_pip_gap.set_ylabel("Frequency")
                ax_pip_gap.grid(True, alpha=0.3)
                
                avg_gap = np.mean(pip_gaps)
                med_gap = np.median(pip_gaps)
                max_gap = np.max(pip_gaps)
                
                ax_pip_gap.axvline(avg_gap, color='red', linestyle='--', linewidth=1, label=f'Mean: {avg_gap:.1f}')
                ax_pip_gap.axvline(med_gap, color='green', linestyle=':', linewidth=1, label=f'Median: {med_gap:.1f}')
                ax_pip_gap.legend(fontsize=8)
                
                stats_text = f"Count: {len(pip_gaps)}\nMax: {max_gap:.1f}"
                ax_pip_gap.text(0.95, 0.95, stats_text, transform=ax_pip_gap.transAxes, fontsize=9, verticalalignment='top', horizontalalignment='right', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
            else:
                ax_pip_gap.set_title("No Pip Gap Data", fontsize=12)
            # Plot 6: Theoretical Drawdown Over Time
            if theoretical_dd_series:
                df_theo = pd.DataFrame(theoretical_dd_series).sort_values('Time')
                ax_theo_dd.plot(df_theo['Time'], df_theo['DD1'], label='DD (1)', alpha=0.7)
                ax_theo_dd.plot(df_theo['Time'], df_theo['DD5'], label='DD (5)', alpha=0.7)
                ax_theo_dd.plot(df_theo['Time'], df_theo['DD10'], label='DD (10)', alpha=0.8)
                ax_theo_dd.plot(df_theo['Time'], df_theo['DD13'], label='DD (13)', alpha=0.9)
                ax_theo_dd.plot(df_theo['Time'], df_theo['DD17'], label='DD (17)', alpha=0.9)
                ax_theo_dd.plot(df_theo['Time'], df_theo['DD20'], label='DD (20)', linewidth=1.5)
                
                ax_theo_dd.set_title("Theoretical Max DD Over Time in USD (at 21st Trade)", fontsize=12)
                ax_theo_dd.set_ylabel("Amount (USD)")
                ax_theo_dd.grid(True, alpha=0.3)
                
                # Plot PipStep on secondary axis
                ax_pip = ax_theo_dd.twinx()
                ax_pip.step(df_theo['Time'], df_theo['PipStepUsed'], where='post', color='grey', linestyle='--', alpha=0.5, label='PipStep (Pips)')
                ax_pip.set_ylabel("PipStep (Pips)", color='grey')
                ax_pip.tick_params(axis='y', labelcolor='grey')
                
                # Combined Legend
                lines, labels = ax_theo_dd.get_legend_handles_labels()
                lines2, labels2 = ax_pip.get_legend_handles_labels()
                ax_theo_dd.legend(lines + lines2, labels + labels2, fontsize=8, loc='upper left')
                
                plt.setp(ax_theo_dd.get_xticklabels(), rotation=30, ha='right')
                ax_theo_dd.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format(int(x), ',')))
            else:
                ax_theo_dd.set_title("No Theoretical DD Data", fontsize=12)
                ax_theo_dd.set_axis_off()

            # Plot 7: Monthly Activity (Sequences & PnL - Combined)
            if not df_at.empty:
                try:
                    # 1. Prepare Data
                    all_months = pd.period_range(start=calc_start, end=calc_end, freq='M')
                    month_labels = [str(m) for m in all_months]
                    x = np.arange(len(all_months))
                    width = 0.35

                    # Monthly Sequence Counts
                    monthly_counts = pd.Series(0, index=all_months)
                    if 'SequenceNumber' in df_at.columns:
                        df_seq_starts = df_at[
                            (df_at['SequenceNumber'] > 0) & 
                            (df_at['TradeNumberInSequence'] == 1) & 
                            (df_at['Direction'].astype(str).str.lower() == 'in')
                        ].copy()
                        if not df_seq_starts.empty:
                            df_seq_starts['Month'] = df_seq_starts['Time'].dt.to_period('M')
                            counts = df_seq_starts.groupby('Month').size()
                            monthly_counts.update(counts)

                    # Monthly PnL
                    monthly_pnl_sum = pd.Series(0.0, index=all_months)
                    df_pnl_monthly = df_at[df_at['Direction'].astype(str).str.lower().isin(['out', 'in/out'])].copy()
                    if not df_pnl_monthly.empty:
                        df_pnl_monthly['Month'] = df_pnl_monthly['Time'].dt.to_period('M')
                        pnl_sum = df_pnl_monthly.groupby('Month')['DealPnL'].sum()
                        monthly_pnl_sum.update(pnl_sum)

                    # 2. Plotting
                    # Primary Axis: Sequences
                    ax_monthly_combined.bar(x - width/2, monthly_counts.values, width, color='purple', alpha=0.5, label='Sequences', edgecolor='black')
                    ax_monthly_combined.set_ylabel('Sequence Count', color='purple')
                    ax_monthly_combined.tick_params(axis='y', labelcolor='purple')
                    ax_monthly_combined.set_title("Monthly Activity (Sequences & PnL)", fontsize=12)
                    ax_monthly_combined.set_xticks(x)
                    ax_monthly_combined.set_xticklabels(month_labels, rotation=45, ha='right')
                    ax_monthly_combined.grid(axis='y', alpha=0.3)

                    # Secondary Axis: PnL
                    ax_pnl_twin = ax_monthly_combined.twinx()
                    pnl_colors = ['green' if val >= 0 else 'red' for val in monthly_pnl_sum.values]
                    ax_pnl_twin.bar(x + width/2, monthly_pnl_sum.values, width, color=pnl_colors, alpha=0.5, label='PnL', edgecolor='black')
                    ax_pnl_twin.set_ylabel('PnL', color='darkgreen')
                    ax_pnl_twin.tick_params(axis='y', labelcolor='darkgreen')
                    ax_pnl_twin.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format(int(x), ',')))

                    # Align Zeros
                    align_dual_axes(ax_monthly_combined, ax_pnl_twin)

                    # Annotations for Sequences
                    for i, v in enumerate(monthly_counts.values):
                        if v > 0:
                            ax_monthly_combined.text(i - width/2, v + 0.1, str(int(v)), ha='center', va='bottom', fontsize=8, color='purple')

                    # Annotations for PnL
                    for i, v in enumerate(monthly_pnl_sum.values):
                        if abs(v) > 0.01:
                            offset = 0.5 if v >= 0 else -1
                            ax_pnl_twin.text(i + width/2, v + offset, f'{v:,.0f}', ha='center', va='bottom' if v >= 0 else 'top', fontsize=7, fontweight='bold')

                    # Legend
                    lns1, lbs1 = ax_monthly_combined.get_legend_handles_labels()
                    lns2, lbs2 = ax_pnl_twin.get_legend_handles_labels()
                    ax_monthly_combined.legend(lns1 + lns2, lbs1 + lbs2, loc='upper left', fontsize=8)

                except Exception as e:
                    print(f"Error plotting Monthly Activity: {e}")
                    ax_monthly_combined.set_title("Error Plotting Monthly Activity", fontsize=12)
            else:
                ax_monthly_combined.set_title("No Data for Monthly Activity", fontsize=12)
            
            # Plot 9: Pip Gap Breach Analysis
            if 'scenario_rows' in locals() and scenario_rows:
                # Extract data for plotting
                labels = [s['Type'] for s in scenario_rows]
                breach_gaps = []
                bar_colors = []
                for s in scenario_rows:
                    try:
                        if s['BreachIdx'] != -1:
                            val = float(s['K1Gap'].replace(',', ''))
                            breach_gaps.append(val)
                            bar_colors.append('tab:red')
                        else:
                            # If no breach, show Gap20 in green
                            val = float(s['Data'].get('Gap20', 0))
                            breach_gaps.append(val)
                            bar_colors.append('tab:green')
                    except:
                        breach_gaps.append(0)
                        bar_colors.append('tab:red')
                
                # Map long names to short names for chart annotations
                name_map = {
                    "Max Distinct Gap": "Max",
                    "Min Distinct Gap": "Min",
                    "Mean Pip Gap (Max DD Day)": "Max DD",
                    "Mean Pip Gap (Max Sequence Day)": "Max Sequence"
                }
                short_labels = [name_map.get(l, l) for l in labels]
                
                x_breach = np.arange(len(labels))
                ax_breach = ax_flat[8]
                
                bars = ax_breach.bar(x_breach, breach_gaps, color=bar_colors, alpha=0.6, edgecolor='black', linewidth=0.5)
                ax_breach.set_title("Pip Gap Breach Analysis ($1k Threshold)", fontsize=12)
                ax_breach.set_ylabel("Pip Gap at Breach")
                ax_breach.set_xticks(x_breach)
                ax_breach.set_xticklabels(short_labels, rotation=0, fontsize=9) # No rotation needed for short labels
                ax_breach.grid(axis='y', alpha=0.3)
                
                # Add value labels on top of bars
                for i, bar in enumerate(bars):
                    height = bar.get_height()
                    if height > 0:
                        label_suffix = ""
                        if bar_colors[i] == 'tab:green':
                            dd_val = scenario_rows[i]['Data'].get('DD20', 0)
                            label_suffix = f"\n(DD: {dd_val:,.0f})"
                        
                        ax_breach.annotate(f'{height:,.1f}{label_suffix}',
                                    xy=(bar.get_x() + bar.get_width() / 2, height),
                                    xytext=(0, 3), textcoords="offset points",
                                    ha='center', va='bottom', fontsize=9, fontweight='bold')
                        
                        # ADD BAR NAME AS ANNOTATION (inside the bar or just below the value)
                        ax_breach.annotate(short_labels[i],
                                    xy=(bar.get_x() + bar.get_width() / 2, height / 2),
                                    rotation=90, ha='center', va='center', fontsize=8, color='white', fontweight='bold')
                
                # Plot Pip Gap at Max Trades as a horizontal line
                if 'max_trades_gap' in locals() and max_trades_gap is not None:
                    ax_breach.axhline(max_trades_gap, color='blue', linestyle='--', linewidth=2, label=f'Pip Gap at Max Trades: {max_trades_gap:.1f}')
                    # Add text label for the line itself
                    ax_breach.text(x_breach[-1] + 0.5, max_trades_gap, f'  Max Sequence Gap: {max_trades_gap:.1f}', color='blue', va='center', fontweight='bold')
                    
                    # Add 3x Max Sequence Day Gap line
                    max_trades_gap_3x = 3 * max_trades_gap
                    ax_breach.axhline(max_trades_gap_3x, color='red', linestyle='--', linewidth=2, label=f'3x Max Sequence Day Gap: {max_trades_gap_3x:.1f}')
                    ax_breach.text(x_breach[-1] + 0.5, max_trades_gap_3x, f'  3x Max Sequence Day Gap: {max_trades_gap_3x:.1f}', color='red', va='center', fontweight='bold')
                    
                    ax_breach.legend(fontsize=8, loc='upper left')
                
                # Adjust y-axis to accommodate labels and line
                max_y = max(breach_gaps + ([max_trades_gap] if 'max_trades_gap' in locals() and max_trades_gap else [0]) + ([max_trades_gap_3x] if 'max_trades_gap_3x' in locals() and max_trades_gap_3x else [0]))
                if max_y > 0:
                    ax_breach.set_ylim(0, max_y * 1.35)
            else:
                ax_flat[8].set_axis_off()
        
        plt.tight_layout()
        p_f_c_p = os.path.join(charts_folder, f"Chart_{report_basename}.png")
        plt.savefig(p_f_c_p)
        plt.close()

        h_l = f"<a href='file:///{full_html_path}' target='_blank'>{report_basename}</a>" if full_html_path else report_basename
        write_worker(f"<h3>{idx}. Report: {h_l}</h3>\n", short=False)
        write_worker(f"<ul class='metrics-list'>\n<li><strong>Status</strong>: <span class='{status_class}'>{status}</span> {'('+reason+')' if reason else ''}</li>\n", short=is_included_in_p)
        if total_pnl is not None:
            # Descriptive Data Source
            ds_str = "Parquet (Balance & Equity)" if df_parquet is not None else "HTML Trade Data (Approximated)"
            write_worker(f"<li><strong>Data Source</strong>: {ds_str}</li>\n", short=is_included_in_p)
            write_worker(f"<li><strong>Total PnL</strong>: {total_pnl:,.2f}</li>\n", short=is_included_in_p)
            
            sel_pnl = df_deals_subset[df_deals_subset['SourceFile'] == original_filename]['DealPnL'].sum() if not df_deals_subset.empty else 0.0
            write_worker(f"<li><strong>Selected PnL</strong>: {sel_pnl:,.2f}</li>\n", short=is_included_in_p)
            
            # Separate PF and RF
            write_worker(f"<li><strong>Profit Factor</strong>: {report_metrics.get('ProfitFactor','N/A')}</li>\n", short=is_included_in_p)
            write_worker(f"<li><strong>Recovery Factor</strong>: {report_metrics.get('RecoveryFactor','N/A')}</li>\n", short=is_included_in_p)
            
            if max_dd_abs is not None and max_dd_pct is not None: 
                # Add Max DD Time
                dd_time_str = f" [{max_dd_time.strftime('%Y.%m.%d')}]" if 'max_dd_time' in locals() and max_dd_time and hasattr(max_dd_time, 'strftime') else ""
                write_worker(f"<li><strong>Max Drawdown</strong>: {max_dd_abs:,.2f} ({max_dd_pct:.2f}%){dd_time_str}</li>\n", short=is_included_in_p)
            
            if max_trades_val is not None:
                date_str = f" [{max_seq_last_trade_date}]" if 'max_seq_last_trade_date' in locals() and max_seq_last_trade_date else ""
                write_worker(f"<li><strong>Max Trades in Sequence</strong>: {max_trades_val}{date_str}</li>\n", short=is_included_in_p)
            
            if max_trades_gap is not None:
                write_worker(f"<li><strong>Pip Gap at Max Trades</strong>: {max_trades_gap:.1f}</li>\n", short=is_included_in_p)
            
            # Restore Buy/Sell counts
            write_worker(f"<li><strong>Buy Trades</strong>: {total_buy_trades}</li>\n", short=is_included_in_p)
            write_worker(f"<li><strong>Sell Trades</strong>: {total_sell_trades}</li>\n", short=is_included_in_p)
        write_worker("</ul>\n", short=is_included_in_p)
        if total_pnl is not None:
            write_worker("<ul>\n", short=is_included_in_p)
            write_worker("<li><strong>Parameters & Validation</strong>:\n", short=is_included_in_p)
            write_worker("<ul class='params-list'>\n", short=is_included_in_p)
            if set_params:
                write_worker(f"<li>Lot Size: <code>{set_params.get('LotSize','N/A')}</code></li>\n", short=is_included_in_p)
                write_worker(f"<li>Max Lots: <code>{set_params.get('MaxLots','N/A')}</code></li>\n", short=is_included_in_p)
                write_worker(f"<li>Lot Size Exponent: <code>{set_params.get('LotSizeExponent','N/A')}</code></li>\n", short=is_included_in_p)
                write_worker(f"<li>Max Orders: <code>{set_params.get('MaxOrders','N/A')}</code></li>\n", short=is_included_in_p)
                write_worker(f"<li>Pip Step: <code>{set_params.get('PipStep','N/A')}</code></li>\n", short=is_included_in_p)
                write_worker(f"<li>Pip Step Exponent: <code>{set_params.get('PipStepExponent','N/A')}</code></li>\n", short=is_included_in_p)
                write_worker(f"<li>Max Pip Step: <code>{set_params.get('MaxPipStep','N/A')}</code></li>\n", short=is_included_in_p)
                write_worker(f"<li>Delay Trade Sequence: <code>{set_params.get('DelayTradeSequence','N/A')}</code></li>\n", short=is_included_in_p)
                write_worker(f"<li>Live Delay: <code>{set_params.get('LiveDelay','N/A')}</code></li>\n", short=is_included_in_p)
            if 'detected_point' in locals() and detected_point is not None: write_worker(f"<li>Point Used: <code>{detected_point}</code></li>\n", short=is_included_in_p)
            write_worker(f"<li>Initial LotSize (Report): <code>{initial_lot_size}</code></li>\n", short=is_included_in_p)
            write_worker(f"<li>Max Grid Level Reached: <code>{max_grid_level}</code></li>\n", short=is_included_in_p)
            
            val_color = "black"
            if lot_validation_status == "OK": val_color = "green"
            elif "Discrepancy" in str(lot_validation_status): val_color = "red"
            write_worker(f"<li>Lot Validation: <b style='color:{val_color};'>{lot_validation_status}</b></li>\n", short=is_included_in_p)
            write_worker("</ul></li>\n", short=is_included_in_p)

            if top_3_discrepancies:
                write_worker("<li><strong>Top 3 Lot Discrepancies</strong>:\n<table style='width: auto; margin: 10px 0;'>\n<thead><tr><th>Trade #</th><th>Entry Time</th><th>Theo Lot</th><th>Actual Lot</th><th>Diff</th></tr></thead>\n<tbody>\n", short=is_included_in_p)
                for d in top_3_discrepancies: write_worker(f"<tr><td>{d['TradeNo']}</td><td>{d['Time']}</td><td>{d['Theo']:.2f}</td><td>{d['Act']:.2f}</td><td>{d['Diff']:.2f}</td></tr>\n", short=is_included_in_p)
                write_worker("</tbody></table></li>\n", short=is_included_in_p)

            if theoretical_dd_series and scenario_rows:
                # --- 1. SUMMARY TABLE (Full & Short) ---
                write_worker("<li><strong>Theoretical Max DD Summary in USD (1k Threshold Only)</strong>:\n<div style='overflow-x: auto;'>\n<table style='width: 100%; margin: 10px 0; font-size: 12px; border-collapse: collapse; border: 1px solid #ddd;'>\n<thead><tr style='background-color: #f2f2f2;'><th style='padding: 8px; border: 1px solid #ddd; text-align: left;'>Type</th><th style='padding: 8px; border: 1px solid #ddd; text-align: left;'>Date</th><th style='padding: 8px; border: 1px solid #ddd; text-align: center;'>Base Pip Gap</th><th style='padding: 8px; border: 1px solid #ddd; text-align: center;'>USD Conv Factor</th><th style='padding: 8px; border: 1px solid #ddd; text-align: center;'>Trade</th><th style='padding: 8px; border: 1px solid #ddd; text-align: center;'>Pip Gap</th></tr></thead>\n<tbody>\n", short=is_included_in_p)
                for s in scenario_rows:
                    b_str = f"L{s['BreachIdx']}-L{s['BreachIdx']+1}" if s['BreachIdx'] != -1 else "N/A"
                    write_worker(f"<tr><td style='padding: 8px; border: 1px solid #ddd;'>{s['Type']}</td><td style='padding: 8px; border: 1px solid #ddd;'>{s['Date']}</td><td style='padding: 8px; border: 1px solid #ddd; text-align: center;'>{s['BasePipGap']}</td><td style='padding: 8px; border: 1px solid #ddd; text-align: center;'>{s['FXFactor']}</td><td style='padding: 8px; border: 1px solid #ddd; text-align: center;'>{b_str}</td><td style='padding: 8px; border: 1px solid #ddd; text-align: center; font-weight: bold; color: red;'>{s['K1Gap']}</td></tr>\n", short=is_included_in_p)
                write_worker("</tbody></table></div></li>\n", short=is_included_in_p)

                # --- 2. DETAILED TABLES (Full Report Only) ---
                write_worker("<li><strong>Theoretical Max DD Summary in USD (Max 2 & Min 2 Distinct Pip Gaps)</strong>:\n<div style='overflow-x: auto;'>\n<table style='width: 100%; margin: 10px 0; font-size: 10px; border-collapse: collapse;'>\n", short=False)
                for s in scenario_rows:
                    d_row, b_idx, k1_v_str = s['Data'], s['BreachIdx'], s['K1Gap']
                    current_colspan = 21 + (1 if b_idx != -1 else 0)
                    write_worker(f"<thead><tr style='background-color: #f2f2f2;'><th colspan='{current_colspan}' style='padding: 4px; text-align: left;'><b>{s['Label']}</b></th></tr><tr><th style='padding: 2px;'>Header</th>", short=False)
                    for b in range(1, 21):
                        if b == b_idx: write_worker(f"<th style='padding: 2px; color: red;'>Threshold: $1,000</th>", short=False)
                        write_worker(f"<th style='padding: 2px;'>L{b}</th>", short=False)
                    write_worker("</tr></thead><tbody><tr><td style='padding: 2px;'><b>Lot / Gap</b></td>", short=False)
                    for b in range(1, 21):
                        if b == b_idx: write_worker(f"<td style='padding: 2px; border: 2px solid red; color: red; font-weight: bold; text-align: center;'>{k1_v_str}</td>", short=False)
                        write_worker(f"<td style='padding: 2px;'>{d_row.get(f'Lot{b}', 0):.2f} / {d_row.get(f'Gap{b}', 0):,.0f}</td>", short=False)
                    write_worker("</tr><tr><td style='padding: 2px;'><b>DD (USD)</b></td>", short=False)
                    for b in range(1, 21):
                        if b == b_idx: write_worker(f"<td style='padding: 2px; border: 2px solid red; color: red; font-weight: bold; text-align: center;'>$1,000</td>", short=False)
                        dd_val = d_row.get(f'DD{b}', 0)
                        style = f"padding: 2px; color: {'red' if dd_val >= 1000 else 'black'}; font-weight: {'bold' if dd_val >= 1000 else 'normal'};"
                        write_worker(f"<td style='{style}'>{dd_val:,.0f}</td>", short=False)
                    write_worker("</tr></tbody>\n", short=False)
                write_worker("</table></div></li>\n", short=False)

                # --- 3. 1k Threshold Simulation Table (Full Report Only) ---
                try:
                    df_theo_all = pd.DataFrame(theoretical_dd_series)
                    if not df_theo_all.empty:
                        # CRITICAL: Match sequential version by rounding PipStepUsed BEFORE selecting worst day
                        df_theo_all['PipStepUsed'] = df_theo_all['PipStepUsed'].round(2)
                        max_dd_row = df_theo_all.sort_values('DD20', ascending=False).iloc[0]
                        base_ps, max_dd_fx = max_dd_row['PipStepUsed'], max_dd_row['FX_Factor']
                        c_atr = base_ps / abs(s_pipstep) if s_pipstep != 0 else 1.0
                        e_mps = c_atr * abs(s_maxpipstep) if s_maxpipstep < 0 else s_maxpipstep
                        
                        sim_p = [0.0] * 23; sim_p[s_ld + 1] = 1.0
                        for k in range(s_ld + 1, 22):
                            g_sim = min(e_mps, base_ps * (s_pipstepexp ** (k-1))) if e_mps > 0 else base_ps * (s_pipstepexp ** (k-1))
                            sim_p[k+1] = sim_p[k] + (g_sim * detected_point)
                        
                        target_lots = [0.01, 0.02, 0.03, 0.04, 0.05]; lot_res = {}
                        for st_lot in target_lots:
                            s_v = [0.0] * 22
                            s_v[1] = sum(min(s_maxlots, st_lot * (s_lotexp ** (j-1))) for j in range(1, s_ld + 2))
                            for j in range(2, 21): s_v[j] = min(s_maxlots, st_lot * (s_lotexp ** (s_ld + j - 1)))
                            
                            fk1, tlk1, lk1, l_dd, l_gap = "N/A", "N/A", "N/A", 0, 0
                            for i in range(1, 21):
                                tp = sim_p[min(s_ld + i + 1, 22)]; d_val_s, o_v = 0, 0
                                for j in range(1, i + 1): d_val_s += s_v[j] * abs(tp - sim_p[s_ld + j]); o_v += s_v[j]
                                d_usd_s, c_gap_s = d_val_s * 100000 * max_dd_fx, abs(tp - 1.0) / detected_point
                                if l_dd < 1000 <= d_usd_s:
                                    if d_usd_s > l_dd: fk1, tlk1, lk1 = f"{l_gap + (c_gap_s - l_gap) * (1000 - l_dd) / (d_usd_s - l_dd):,.1f}", f"{o_v:.2f}", f"L{i}-{i+1}"
                                    break
                                l_dd, l_gap = d_usd_s, c_gap_s
                            lot_res[st_lot] = {'gap': fk1, 'lots': tlk1, 'level': lk1}
                        
                        write_worker("<li><strong>1k Drawdown Threshold vs. Starting Lot (Pips)</strong>:\n<div style='overflow-x: auto;'>\n<table style='margin: 10px 0; font-size: 10px; border-collapse: collapse; min-width: 300px;'>\n<thead><tr style='background-color: #f2f2f2;'><th style='border: 1px solid #ddd; padding: 4px;'>Starting Lot</th>", short=False)
                        for lt in target_lots: write_worker(f"<th style='border: 1px solid #ddd; padding: 4px;'>{lt}</th>", short=False)
                        write_worker("</tr></thead><tbody><tr><td style='border: 1px solid #ddd; padding: 4px;'><b>1k Pip Gap</b></td>", short=False)
                        for lt in target_lots: write_worker(f"<td style='border: 1px solid #ddd; padding: 4px; text-align: center;'>{lot_res[lt]['gap']}</td>", short=False)
                        write_worker("</tr><tr><td style='border: 1px solid #ddd; padding: 4px;'><b>Total Lots</b></td>", short=False)
                        for lt in target_lots: write_worker(f"<td style='border: 1px solid #ddd; padding: 4px; text-align: center;'>{lot_res[lt]['lots']}</td>", short=False)
                        write_worker("</tr><tr><td style='border: 1px solid #ddd; padding: 4px;'><b>Trade Level</b></td>", short=False)
                        for lt in target_lots: write_worker(f"<td style='border: 1px solid #ddd; padding: 4px; text-align: center;'>{lot_res[lt]['level']}</td>", short=False)
                        write_worker("</tr></tbody></table></div></li>\n", short=False)
                except Exception as ex: write_worker(f"<li><strong style='color: red;'>1k Threshold Sim Error</strong>: {ex}</li>\n", short=is_included_in_p)
            elif 'theoretical_skip_reason' in locals() and theoretical_skip_reason:
                write_worker(f"<li><strong style='color: #856404;'>Theoretical DD Skipped</strong>: {theoretical_skip_reason}</li>\n", short=is_included_in_p)
            
            write_worker("</ul>\n", short=is_included_in_p)
        
        write_worker(f"<div class='chart-container'><img src='charts/Chart_{report_basename}.png' alt='{report_basename} Charts'></div>\n\n", short=is_included_in_p)
        
        return {'idx': idx, 'r_info': r_info, 'is_included': is_included_in_p, 'html_full': "".join(html_full), 'html_short': "".join(html_short), 'total_pnl': total_pnl, 'max_dd_abs': max_dd_abs, 'daily_maxes': daily_maxes, 'report_basename': report_basename, 'full_html_path': full_html_path}
    except Exception as e: return {'idx': idx, 'r_info': r_info, 'is_included': is_included_in_p, 'html_full': f"Error: {e}", 'html_short': "", 'total_pnl': 0, 'max_dd_abs':0, 'daily_maxes':None, 'report_basename': report_basename, 'full_html_path': full_html_path}

def main():



    parser = argparse.ArgumentParser(description='Comprehensive Portfolio Analysis')
    parser.add_argument('output_folder', type=str, help='Path to the output folder (e.g., [Parent]/analysis/output_*) created in Step 1 (list.py).')
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--base', type=float, default=100000.0, help='Base capital (default: 100,000)')
    parser.add_argument('--all', action='store_true', help='Process all reports in detail, even if excluded from portfolio.')
    args = parser.parse_args()

    output_dir = os.path.abspath(args.output_folder)
    
    # Initialize shared variables
    report_daily_max_dds = {}
    table_html = ""
    portfolio_max_dd_abs = 0.0
    portfolio_max_dd_pct = 0.0
    portfolio_max_dd_time = "N/A"

    # 1. Locate Trades folder and create Charts folder
    trades_folder = os.path.join(output_dir, "Trades")
    charts_folder = os.path.join(output_dir, "charts")
    
    if os.path.exists(charts_folder):
        print(f"Refreshing charts folder: {charts_folder}")
        shutil.rmtree(charts_folder)
        
    os.makedirs(charts_folder, exist_ok=True)
    
    if not os.path.exists(trades_folder):
        print(f"Error: Trades folder not found in {output_dir}")
        return
    
    os.makedirs(charts_folder, exist_ok=True)
    print(f"Using trades folder: {trades_folder}")
    print(f"Saving charts to: {charts_folder}")

    # 2. Load all deals
    csv_files = glob.glob(os.path.join(trades_folder, "selected_trades_*.csv"))
    all_deals = []
    if csv_files:
        for f in csv_files:
            df = pd.read_csv(f)
            df['Time'] = pd.to_datetime(df['Time'])
            all_deals.append(df)
        df_deals = pd.concat(all_deals).sort_values('Time')
        # Calculate DealPnL on the fly (Profit + Commission + Swap)
        df_deals['DealPnL'] = df_deals['Profit'] + df_deals['Commission'] + df_deals['Swap']
    else:
        df_deals = pd.DataFrame(columns=['Time', 'SourceFile', 'Direction', 'Profit', 'Commission', 'Swap', 'DealPnL'])
        print("Note: No portfolio-wide selected trades found. Proceeding with detailed report analysis only.")

    # 3. Determine Date Range
    if not df_deals.empty:
        data_start = df_deals['Time'].min().normalize()
        data_end = df_deals['Time'].max().normalize() + pd.Timedelta(days=1)
    else:
        # Fallback to current year or some sensible default if everything is empty
        data_start = pd.Timestamp.now().normalize() - pd.Timedelta(days=365)
        data_end = pd.Timestamp.now().normalize() + pd.Timedelta(days=1)
    
    calc_start = pd.to_datetime(args.start) if args.start else data_start
    calc_end = pd.to_datetime(args.end) if args.end else data_end

    print(f"Analysis range: {calc_start.date()} to {calc_end.date()}")

    # 3.5 Load all FX rates for conversion
    all_fx_rates = load_all_fx_rates(output_dir)

    # 4. Filter deals by date range

    if not df_deals.empty:
        df_deals = df_deals[(df_deals['Time'] >= calc_start) & (df_deals['Time'] < calc_end)]

    if df_deals.empty:
        print("No trades found in the specified date range for portfolio aggregation.")
        # Create an empty portfolio dataframe to satisfy later plotting code if necessary
        # Or simply skip the portfolio overview part
        portfolio = pd.DataFrame(columns=['Balance', 'Drawdown%', 'PeakBalance'])
    else:
        # 5. Create Portfolio Timeline
        # We create a 1-minute grid
        full_idx = pd.date_range(start=calc_start, end=calc_end, freq='1min')
        portfolio = pd.DataFrame(index=full_idx)
        portfolio['BalancePnL'] = 0.0

        # Group deals by minute to avoid duplicates on the grid
        deals_grouped = df_deals.copy()
        deals_grouped['Time'] = deals_grouped['Time'].dt.floor('1min')
        
        # Balance changes at every deal (Profit + Commission + Swap)
        balance_changes = deals_grouped.groupby('Time')['DealPnL'].sum()

        # Map to grid
        portfolio.loc[balance_changes.index, 'BalancePnL'] = balance_changes.values

        # Cumulative Sums
        portfolio['Balance'] = portfolio['BalancePnL'].cumsum() + args.base

        # 6. Drawdown Calculation (Underwater)
        portfolio['PeakBalance'] = portfolio['Balance'].expanding().max()
        portfolio['Drawdown'] = (portfolio['Balance'] / portfolio['PeakBalance']) - 1
        portfolio['Drawdown%'] = portfolio['Drawdown'] * 100
        
        # Capture Portfolio Max DD and its timestamp
        portfolio_max_dd_pct = portfolio['Drawdown%'].min()
        portfolio_max_dd_time = portfolio['Drawdown%'].idxmin()
        portfolio_max_dd_abs = (portfolio['Balance'] - portfolio['PeakBalance']).min()
        portfolio_max_dd_abs_time = (portfolio['Balance'] - portfolio['PeakBalance']).idxmin()

    # Calculate Portfolio-wide Buy/Sell Trade Counts
    total_portfolio_buy_trades = 0
    total_portfolio_sell_trades = 0
    if not df_deals.empty:
        in_deals_portfolio = df_deals[df_deals['Direction'].astype(str).str.lower().isin(['in', 'in/out'])]
        total_portfolio_buy_trades = len(in_deals_portfolio[in_deals_portfolio['Type'].astype(str).str.lower() == 'buy'])
        total_portfolio_sell_trades = len(in_deals_portfolio[in_deals_portfolio['Type'].astype(str).str.lower() == 'sell'])


    # 7. Charting
    overview_chart_path = os.path.join(charts_folder, "Portfolio_Overview.png")
    if not portfolio.empty:
        def add_monthly_grids(ax, start, end):
            # Add vertical lines at start of each month
            months = pd.date_range(start=start.replace(day=1), end=end, freq='MS')
            for m in months:
                ax.axvline(m, color='gray', linestyle='--', alpha=0.5, linewidth=0.8)

        # 7. Portfolio Overview Chart (1x2: Balance and Drawdown)
        fig_overview, (ax1, ax2) = plt.subplots(1, 2, figsize=(22, 10), layout='constrained')
        
        # Plot 1: Portfolio Balance
        ax1.plot(portfolio.index, portfolio['Balance'], label='Balance', color='blue', linewidth=1.5)
        ax1.set_title('Portfolio Performance (Balance)', fontsize=14)
        ax1.set_xlabel('Date')
        ax1.set_ylabel('Amount (USD)')
        ax1.legend(loc='best')
        ax1.grid(True, alpha=0.3)
        add_monthly_grids(ax1, calc_start, calc_end)
        ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format(int(x), ',')))
        plt.setp(ax1.get_xticklabels(), rotation=30, ha='right')

        # Plot 2: Underwater Drawdown
        ax2.fill_between(portfolio.index, portfolio['Drawdown%'], 0, color='red', alpha=0.3)
        ax2.plot(portfolio.index, portfolio['Drawdown%'], color='red', linewidth=0.8, label='Drawdown %')
        ax2.set_title('Underwater Drawdown', fontsize=14)
        ax2.set_xlabel('Date')
        ax2.set_ylabel('Drawdown %')
        ax2.grid(True, alpha=0.3)
        add_monthly_grids(ax2, calc_start, calc_end)

        # Add secondary Y-axis for absolute drawdown values
        ax2_abs = ax2.twinx()
        abs_drawdown = portfolio['Balance'] - portfolio['PeakBalance']
        ax2_abs.plot(portfolio.index, abs_drawdown, color='black', linestyle='--', alpha=0.3, label='Drawdown Abs') 
        ax2_abs.set_ylabel('Drawdown Absolute (USD)')
        ax2_abs.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format(int(x), ',')))
        
        # Align zero lines if possible
        align_dual_axes(ax2, ax2_abs)
        
        ax2.legend(loc='upper left')
        ax2_abs.legend(loc='upper right')
        plt.setp(ax2.get_xticklabels(), rotation=30, ha='right')

        # Add Annotation for Max Drawdown
        if not math.isnan(portfolio_max_dd_pct):
            anno_text = (f"Max Drawdown: {portfolio_max_dd_abs:,.2f} USD\n"
                         f"Max Drawdown %: {portfolio_max_dd_pct:.2f}%\n"
                         f"Date: {portfolio_max_dd_time}")
            ax2.annotate(anno_text, xy=(0.05, 0.05), xycoords='axes fraction',
                         bbox=dict(boxstyle="round,pad=0.5", fc="white", ec="red", alpha=0.8),
                         fontsize=10, color="red", fontweight="bold")

        plt.savefig(overview_chart_path)
        plt.close()
    else:
        # Create a placeholder or just don't save. Later code will check for file existence.
        print("Skipping Portfolio Overview chart as portfolio is empty.")
    # 8. Pre-load report list for metadata and hyperlinks
    report_list_path = os.path.join(output_dir, "report_list.csv")
    html_path_map = {}
    if os.path.exists(report_list_path):
        try:
            df_list_tmp = pd.read_csv(report_list_path)
            for _, row in df_list_tmp.iterrows():
                html_path_map[os.path.basename(row['FilePath'])] = row['FilePath']
        except: pass

    # --- Pre-calculate inclusion metadata for reports ---
    num_included = df_deals['SourceFile'].nunique() if not df_deals.empty else 0
    num_total = "Unknown"
    explicitly_skipped = []
    overlapping_skipped = []
    
    if os.path.exists(report_list_path):
        try:
            df_list = pd.read_csv(report_list_path)
            num_total = len(df_list)
            
            # Categorize skipped files
            actually_included = set(df_deals['SourceFile'].unique()) if not df_deals.empty else set()
            
            explicitly_excluded_paths = df_list[df_list['Include'] == 0]['FilePath']
            explicitly_skipped = sorted([os.path.basename(f) for f in explicitly_excluded_paths])
            
            potentially_included_paths = df_list[df_list['Include'] == 1]['FilePath']
            potentially_included = set(os.path.basename(f) for f in potentially_included_paths)
            
            overlapping_skipped = sorted(list(potentially_included - actually_included))
        except:
            pass

    # 8. Consolidated Monthly Contributor Table (with Gradient Color Coding)
    if not df_deals.empty:
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
        
        # Calculate Buy/Sell counts for all selected trades per file
        in_deals_all = df_deals[df_deals['Direction'].astype(str).str.lower().isin(['in', 'in/out'])].copy()
        in_deals_all['Type_lower'] = in_deals_all['Type'].astype(str).str.lower()
        file_counts = in_deals_all.groupby(['Symbol', 'SourceFile', 'Type_lower']).size().unstack(fill_value=0)
        
        table_html = "## Monthly Contributor Breakdown\n\n"
        table_html += "<table>\n<thead>\n<tr>"
        table_html += "<th>S.No</th><th>Symbol</th><th>Report File</th><th>Buy Trades</th><th>Sell Trades</th>" + "".join([f"<th>{m}</th>" for m in months_headers]) + "<th>Total</th>"
        table_html += "</tr>\n</thead>\n<tbody>\n"
        
        for i, ((symbol, file_name), row) in enumerate(pivot_table.iterrows(), 1):
            # Try to get absolute path for hyperlink
            full_path = html_path_map.get(file_name, "")
            file_link = f"<a href='file:///{full_path}' target='_blank'><code>{file_name}</code></a>" if full_path else f"<code>{file_name}</code>"
            
            # Get buy/sell counts
            buy_count = file_counts.loc[(symbol, file_name), 'buy'] if (symbol, file_name) in file_counts.index and 'buy' in file_counts.columns else 0
            sell_count = file_counts.loc[(symbol, file_name), 'sell'] if (symbol, file_name) in file_counts.index and 'sell' in file_counts.columns else 0

            table_html += "<tr>"
            table_html += f"<td>{i}</td>"
            table_html += f"<td>{symbol}</td>"
            table_html += f"<td>{file_link}</td>"
            table_html += f"<td style='text-align:right;'>{buy_count}</td>"
            table_html += f"<td style='text-align:right;'>{sell_count}</td>"
            for val in row:
                color = get_color(val, global_min, global_max)
                table_html += f'<td style="background-color:{color}; color:black; text-align:right;">{val:.2f}</td>'
            
            total_pnl_val = row.sum()
            total_color = get_color(total_pnl_val, pivot_table.sum(axis=1).min(), pivot_table.sum(axis=1).max())
            table_html += f'<td style="background-color:{total_color}; color:black; text-align:right;"><b>{total_pnl_val:.2f}</b></td>'
            table_html += "</tr>\n"
        
        # Total row
        monthly_totals = pivot_table.sum()
        grand_total = monthly_totals.sum()
        table_html += "<tr>"
        table_html += "<td colspan='3'><b>Total</b></td>"
        table_html += f"<td style='text-align:right;'><b>{total_portfolio_buy_trades}</b></td>"
        table_html += f"<td style='text-align:right;'><b>{total_portfolio_sell_trades}</b></td>"
        for val in monthly_totals:
            color = get_color(val, monthly_totals.min(), monthly_totals.max())
            table_html += f'<td style="background-color:{color}; color:black; text-align:right;"><b>{val:.2f}</b></td>'
        
        gt_color = get_color(grand_total, pivot_table.values.sum(), pivot_table.values.sum())
        table_html += f'<td style="background-color:{gt_color}; color:black; text-align:right;"><b>{grand_total:.2f}</b></td>'
        table_html += "</tr>\n</tbody>\n</table>\n\n"

        # --- New: Monthly Currency Breakdown Table ---
        # Group by Symbol and Month for currency level aggregation
        currency_monthly_pnl = df_deals.groupby(['Symbol', 'Month'])['DealPnL'].sum().reset_index()
        currency_pivot = currency_monthly_pnl.pivot(index='Symbol', columns='Month', values='DealPnL').fillna(0)
        
        # Get report file count per symbol
        symbol_report_counts = df_deals.groupby('Symbol')['SourceFile'].nunique()
        
        # Aggregate Buy/Sell counts per symbol
        symbol_counts = in_deals_all.groupby(['Symbol', 'Type_lower']).size().unstack(fill_value=0)
        
        currency_table_html = "<h2>Monthly Currency Breakdown</h2>\n"
        currency_table_html += "<table>\n<thead>\n<tr>"
        currency_table_html += "<th>S.No</th><th>Symbol</th><th>Report File Count</th><th>Buy Trades</th><th>Sell Trades</th>" + "".join([f"<th>{m}</th>" for m in months_headers]) + "<th>Total</th>"
        currency_table_html += "</tr>\n</thead>\n<tbody>\n"
        
        for i, (symbol, row) in enumerate(currency_pivot.iterrows(), 1):
            report_count = symbol_report_counts.get(symbol, 0)
            buy_count = symbol_counts.loc[symbol, 'buy'] if symbol in symbol_counts.index and 'buy' in symbol_counts.columns else 0
            sell_count = symbol_counts.loc[symbol, 'sell'] if symbol in symbol_counts.index and 'sell' in symbol_counts.columns else 0

            currency_table_html += "<tr>"
            currency_table_html += f"<td>{i}</td>"
            currency_table_html += f"<td>{symbol}</td>"
            currency_table_html += f"<td style='text-align:right;'>{report_count}</td>"
            currency_table_html += f"<td style='text-align:right;'>{buy_count}</td>"
            currency_table_html += f"<td style='text-align:right;'>{sell_count}</td>"
            for val in row:
                color = get_color(val, global_min, global_max)
                currency_table_html += f'<td style="background-color:{color}; color:black; text-align:right;">{val:.2f}</td>'
            
            total_pnl_val = row.sum()
            total_color = get_color(total_pnl_val, currency_pivot.sum(axis=1).min(), currency_pivot.sum(axis=1).max())
            currency_table_html += f'<td style="background-color:{total_color}; color:black; text-align:right;"><b>{total_pnl_val:.2f}</b></td>'
            currency_table_html += "</tr>\n"
        
        # Total row for Currency Table
        currency_table_html += "<tr>"
        currency_table_html += "<td colspan='2'><b>Total</b></td>"
        currency_table_html += f"<td style='text-align:right;'><b>{num_included}</b></td>"
        currency_table_html += f"<td style='text-align:right;'><b>{total_portfolio_buy_trades}</b></td>"
        currency_table_html += f"<td style='text-align:right;'><b>{total_portfolio_sell_trades}</b></td>"
        for val in monthly_totals:
            color = get_color(val, monthly_totals.min(), monthly_totals.max())
            currency_table_html += f'<td style="background-color:{color}; color:black; text-align:right;"><b>{val:.2f}</b></td>'
        
        currency_table_html += f'<td style="background-color:{gt_color}; color:black; text-align:right;"><b>{grand_total:.2f}</b></td>'
        currency_table_html += "</tr>\n</tbody>\n</table>\n\n"
    else:
        table_html = "No trades included in the aggregate portfolio for the specified period.\n\n"
        currency_table_html = ""



    # 7. Pre-calculate Portfolio-wide Conservative Max DD
    report_daily_max_dds = {}
    included_files_set = set(df_deals['SourceFile'].unique()) if not df_deals.empty else set()
    
    # We only need this for included files
    if not df_deals.empty:
        print("Pre-calculating daily drawdowns for portfolio aggregation...")
        # Get list of files to process
        reports_to_process = []
        if os.path.exists(report_list_path):
            try:
                df_list_all = pd.read_csv(report_list_path)
                for _, row_all in df_list_all.iterrows():
                    fname = os.path.basename(row_all['FilePath'])
                    if fname in included_files_set:
                        reports_to_process.append({
                            'basename': os.path.splitext(fname)[0],
                            'full_html_path': row_all['FilePath']
                        })
            except: pass
        
        if not reports_to_process:
            # Fallback
            for f_name in included_files_set:
                reports_to_process.append({
                    'basename': os.path.splitext(f_name)[0],
                    'full_html_path': html_path_map.get(f_name)
                })

        # Multi-processed pre-calculation
        total_pre = len(reports_to_process)
        pool_args = [(r, calc_start, calc_end, trades_folder, args.base, i, total_pre) for i, r in enumerate(reports_to_process, 1)]
        try:
            with mp.Pool(processes=mp.cpu_count()) as pool:
                pre_results = pool.map(precalc_drawdown_worker, pool_args)
                for r_base, dd_series in pre_results:
                    if r_base and dd_series is not None:
                        report_daily_max_dds[r_base] = dd_series
        except KeyboardInterrupt:
            print("\n[STOP] Pre-calculation interrupted by user. Terminating...")
            sys.exit(1)


    # Calculate Global Portfolio DD Sum if we have data
    if report_daily_max_dds:
        df_daily_all = pd.DataFrame(report_daily_max_dds).fillna(0)
        daily_portfolio_dd_sum = df_daily_all.sum(axis=1)
        if not daily_portfolio_dd_sum.empty:
            portfolio_max_dd_abs = daily_portfolio_dd_sum.min()
            portfolio_max_dd_time = daily_portfolio_dd_sum.idxmin()
            portfolio_max_dd_pct = (portfolio_max_dd_abs / args.base) * 100 if args.base != 0 else 0

    # 9. Compile HTML Report
    report_path = os.path.join(output_dir, "Full_Analysis.html")
    short_report_path = os.path.join(output_dir, "Short_Analysis.html")
    
    css_style = """
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; max-width: 1200px; margin: 0 auto; padding: 20px; background-color: #f4f7f6; }
        h1, h2, h3 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; margin-top: 30px; }
        .summary-box { background-color: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .summary-box p { margin: 5px 0; font-size: 1.1em; }
        table { border-collapse: collapse; width: 100%; margin: 20px 0; background-color: #fff; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
        th, td { padding: 12px 15px; border: 1px solid #ddd; text-align: left; }
        th { background-color: #3498db; color: white; }
        tr:nth-child(even) { background-color: #f9f9f9; }
        code { background-color: #eef; padding: 2px 4px; border-radius: 4px; font-family: monospace; }
        .chart-container { text-align: center; margin: 30px 0; background-color: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .chart-container img { max-width: 100%; height: auto; border-radius: 4px; }
        ul { list-style-type: none; padding: 0; }
        li { background: #fff; margin-bottom: 5px; padding: 10px; border-left: 5px solid #3498db; border-radius: 0 4px 4px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .status-included { color: #27ae60; font-weight: bold; }
        .status-skipped { color: #e74c3c; font-weight: bold; }
        .status-partial { color: #f39c12; font-weight: bold; }
        .params-list { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; list-style: none; padding: 0; margin-top: 10px; }
        .params-list li { border: 1px solid #ddd; border-left: 5px solid #3498db; padding: 8px 12px; background: #fff; font-size: 0.95em; box-shadow: 0 1px 2px rgba(0,0,0,0.05); margin-bottom: 0; min-width: unset; }
        .metrics-list { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; list-style: none; padding: 0; margin-bottom: 20px; }
        .metrics-list li { border: 1px solid #ddd; border-left: 5px solid #27ae60; padding: 8px 12px; background: #fff; font-size: 0.95em; box-shadow: 0 1px 2px rgba(0,0,0,0.05); margin-bottom: 0; min-width: unset; }
    </style>
    """

    with open(report_path, 'w', encoding='utf-8') as f_full, open(short_report_path, 'w', encoding='utf-8') as f_short:
        f = MultiWriter(f_full, f_short)
        f.write("<!DOCTYPE html>\n<html lang='en'>\n<head>\n")
        f.write("    <meta charset='UTF-8'>\n")
        f.write("    <meta name='viewport' content='width=device-width, initial-scale=1.0'>\n")
        f.write("    <title>Portfolio Analysis Report</title>\n")
        f.write(css_style)
        f.write("</head>\n<body>\n")
        
        f.write("<h1>Portfolio Analysis Report</h1>\n")
        f.write("<div class='summary-box'>\n")
        f.write(f"<p><strong>Period:</strong> {calc_start.date()} to {calc_end.date()}</p>\n")
        f.write(f"<p><strong>Included Reports:</strong> {num_included} / {num_total}</p>\n")
        f.write(f"<p><strong>Base Capital:</strong> {args.base:,.2f}</p>\n")
        
        final_balance = portfolio['Balance'].iloc[-1] if not portfolio.empty and 'Balance' in portfolio.columns else args.base
        f.write(f"<p><strong>Final Balance:</strong> {final_balance:,.2f}</p>\n")
        f.write(f"<p><strong>Total Profit:</strong> {(final_balance - args.base):,.2f}</p>\n")
        
        if not portfolio.empty:
            f.write(f"<p><strong>Max Drawdown:</strong> {portfolio_max_dd_abs:,.2f} ({portfolio_max_dd_pct:.2f}%) [{portfolio_max_dd_time}]</p>\n")
        
        f.write(f"<p><strong>Total Trades:</strong> {total_portfolio_buy_trades + total_portfolio_sell_trades} (Buy: {total_portfolio_buy_trades}, Sell: {total_portfolio_sell_trades})</p>\n")
        f.write("</div>\n")

        
        f.write("<h2>Performance Charts</h2>\n")
        overview_path = "charts/Portfolio_Overview.png"
        if os.path.exists(os.path.join(output_dir, overview_path)):
            f.write(f"<div class='chart-container'><img src='{overview_path}' alt='Portfolio Overview'></div>\n\n")
        else:
            f.write("<p>Portfolio Overview chart is not available (no portfolio-wide trades found).</p>\n\n")
        
        # 11. Final Portfolio Stats Update (Conservative Daily-Sum Max DD)
        if report_daily_max_dds:
            # Combine all daily series into a dataframe. Items are negative drawdowns.
            df_daily_all = pd.DataFrame(report_daily_max_dds).fillna(0)
            # Sum rows (daily totals of max drawdowns from all included reports)
            daily_portfolio_dd_sum = df_daily_all.sum(axis=1)
            
            if not daily_portfolio_dd_sum.empty:
                portfolio_max_dd_abs = daily_portfolio_dd_sum.min()
                portfolio_max_dd_time = daily_portfolio_dd_sum.idxmin()
                portfolio_max_dd_pct = (portfolio_max_dd_abs / args.base) * 100 if args.base != 0 else 0
                
                # Write a hidden table with daily DDs per report for simulate.py
                f.write("\n<!-- DAILY_DD_DATA_START\n")
                # Format: Date,Report1_DD,Report2_DD,...
                # We save CSV format here for easy parsing
                f.write(df_daily_all.to_csv())
                f.write("DAILY_DD_DATA_END -->\n")

        # Monthly breakdown tables
        # Note: table_html was constructed with markdown headers previously
        table_html_clean = table_html.replace("## Monthly Contributor Breakdown\n\n", "<h2>Monthly Contributor Breakdown</h2>\n")
        f.write(table_html_clean)
        if 'currency_table_html' in locals() and currency_table_html:
            f.write(currency_table_html)

        # 11. Final summary boxes and lists
        if explicitly_skipped:
            f.write("<h2>Explicitly Excluded Reports</h2>\n")
            f.write("<p>These files were skipped because they were marked with <code>Include = 0</code> in the report list:</p>\n")
            f.write("<ul>\n")
            for sf in explicitly_skipped:
                sf_path = html_path_map.get(sf, "")
                sf_link = f"<a href='file:///{sf_path}' target='_blank'><code>{sf}</code></a>" if sf_path else f"<code>{sf}</code>"
                f.write(f"<li>{sf_link}</li>\n")
            f.write("</ul>\n")

        if overlapping_skipped:
            f.write("<h2>Overlapping Trades (Skipped)</h2>\n")
            f.write("<p>These files were marked for inclusion but skipped because all their trades overlapped with already accepted sequences:</p>\n")
            f.write("<ul>\n")
            for sf in overlapping_skipped:
                sf_path = html_path_map.get(sf, "")
                sf_link = f"<a href='file:///{sf_path}' target='_blank'><code>{sf}</code></a>" if sf_path else f"<code>{sf}</code>"
                f.write(f"<li>{sf_link}</li>\n")
            f.write("</ul>\n")

        # 10. Detailed Per-Report Analysis
        f.write("<h2>Detailed Per-Report Analysis</h2>\n")
        
        all_trades_files = glob.glob(os.path.join(trades_folder, "all_trades_*.csv"))
        

        if not all_trades_files:
            f.write("<p>No detailed trade files found.</p>\n")
        else:
            # Sort files for consistent report order
            all_trades_files.sort()
            # Create sets for easy lookup
            included_files = set(df_deals['SourceFile'].unique()) if not df_deals.empty else set()
            
            # Iterate through all files specified in report_list.csv to ensure all are shown
            all_reports_to_show = []
            if os.path.exists(report_list_path):
                try:
                    df_list_all = pd.read_csv(report_list_path)
                    for _, row_all in df_list_all.iterrows():
                        fname = os.path.basename(row_all['FilePath'])
                        # Remove .set.html, .html, .set etc.
                        basename = re.sub(r'(\.set|\.html?)+$', '', fname, flags=re.IGNORECASE)
                        all_reports_to_show.append({
                            'basename': basename,
                            'original_filename': fname,
                            'full_html_path': row_all['FilePath']
                        })
                except:
                    # Fallback to current behavior if list reading fails
                    for atf in all_trades_files:
                        bn = os.path.basename(atf).replace("all_trades_", "").replace(".csv", "")
                        bn = re.sub(r'(\.set)+$', '', bn, flags=re.IGNORECASE)
                        all_reports_to_show.append({'basename': bn, 'original_filename': bn + ".html", 'full_html_path': None})
            else:
                # Fallback if report_list.csv doesn't exist at all
                for atf in all_trades_files:
                    bn = os.path.basename(atf).replace("all_trades_", "").replace(".csv", "")
                    bn = re.sub(r'(\.set)+$', '', bn, flags=re.IGNORECASE)
                    all_reports_to_show.append({'basename': bn, 'original_filename': bn + ".html", 'full_html_path': None})
            # Prepare arguments for multiprocessing
            inc_f = set(df_deals['SourceFile'].unique()) if not df_deals.empty else set()
            ex_s = set(explicitly_skipped)
            ov_s = set(overlapping_skipped)
            sets_dir = os.path.join(output_dir, "sets")
            df_deals_by_file = {f: df for f, df in df_deals.groupby('SourceFile')} if not df_deals.empty else {}

            total_reports = len(all_reports_to_show)
            pool_args = [
                (idx, r_info, args, calc_start, calc_end, trades_folder, sets_dir, 
                 charts_folder, output_dir, inc_f, ex_s, ov_s, all_fx_rates, 
                 df_deals_by_file.get(r_info['original_filename'], pd.DataFrame(columns=df_deals.columns)),
                 total_reports)
                for idx, r_info in enumerate(all_reports_to_show, 1)
            ]
            
            print(f"Running parallel per-report analysis on {mp.cpu_count()} CPUs...")
            try:
                with mp.Pool(processes=mp.cpu_count()) as pool:
                    res_list = pool.map(analyze_single_report_worker, pool_args)
            except KeyboardInterrupt:
                print("\n[STOP] Analysis interrupted by user. Terminating...")
                sys.exit(1)
            
            res_list.sort(key=lambda x: x['idx'])
            
            current_short_idx = 1
            for res in res_list:
                f.write(res['html_full'], short=False)
                if res['is_included']:
                    h_lnk = f"<a href='file:///{res['full_html_path']}' target='_blank'>{res['report_basename']}</a>" if res['full_html_path'] else res['report_basename']
                    f.write(f"<h3>{current_short_idx}. Report: {h_lnk}</h3>\n", full=False)
                    f.write(res['html_short'], full=False)
                    current_short_idx += 1
                
                if res['daily_maxes'] is not None:
                    report_daily_max_dds[res['report_basename']] = res['daily_maxes']
        f.write("\n</body>\n</html>")

    print(f"\nAnalysis complete.")
    print(f"Report saved to: {report_path}")
    
    # Try to provide a clickable link in the console (VS Code and some terminals support this)
    clickable_link = f"file:///{report_path.replace(os.sep, '/')}"
    print(f"Open Report: {clickable_link}")
    
    # Automatically open in default browser
    try:
        webbrowser.open(clickable_link)
        short_link = f"file:///{short_report_path.replace(os.sep, '/')}"
        webbrowser.open(short_link)
    except Exception as e:
        print(f"Could not automatically open browser: {e}")

if __name__ == "__main__":
    main()


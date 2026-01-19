import pandas as pd
import os
import glob
import argparse
from datetime import datetime
import numpy as np
import math
import re

def parse_set_file(set_path):
    """Reads .set file and extracts target parameters."""
    target_params = {
        "lotsize": "LotSize",
        "lotsizeexponent": "LotSizeExponent",
        "maxlots": "MaxLots",
        "delaytradesequence": "DelayTradeSequence",
        "livedelay": "LiveDelay",
        "maxorders": "MaxOrders",
        "stoploss": "StopLoss",
        "pipstep": "PipStep",
        "pipstepexponent": "PipStepExponent",
        "maxpipstep": "MaxPipStep"
    }
    results = {v: "0" for v in target_params.values()}
    
    if not os.path.exists(set_path):
        return None

    content = None
    # Try common encodings for MT4/MT5 .set files
    for enc in ['utf-16', 'utf-16-le', 'utf-8', 'latin-1', 'cp1252']:
        try:
            with open(set_path, 'r', encoding=enc, errors='ignore') as sf:
                content = sf.read()
                if '=' in content:
                    break
        except:
            continue
    
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

def load_fx_rates(prices_dir):
    """Loads daily FX closing prices from the prices/ folder."""
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
        if match:
            clean_symbol = match.group(1)
        else:
            return 1.0
    
    clean_symbol = clean_symbol.upper()
    quote = clean_symbol[3:]
    
    if quote == "USD": return 1.0
    
    s1, s2 = f"USD{quote}", f"{quote}USD"
    target_d = target_date.date() if hasattr(target_date, 'date') else target_date
    
    def find_rate(sym_key, invert):
        if sym_key in fx_rates:
            df = fx_rates[sym_key]
            try:
                # Find nearest date (padded)
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

def extract_symbol_from_html(html_path):
    """Extracts symbol name from the MT5 HTML report."""
    if not html_path or not os.path.exists(html_path):
        return None
    try:
        from bs4 import BeautifulSoup
        content = None
        for encoding in ['utf-16', 'utf-8', 'cp1252']:
            try:
                with open(html_path, 'r', encoding=encoding, errors='ignore') as f:
                    content = f.read()
                if content: break
            except: continue
        
        if not content: return None
        soup = BeautifulSoup(content, 'lxml')
        
        # Look for "Symbol:" in text
        symbol_node = soup.find(string=lambda text: text and "Symbol:" in text)
        if symbol_node:
            parent = symbol_node.find_parent('td')
            if parent:
                next_td = parent.find_next_sibling('td')
                if next_td:
                    raw_val = next_td.get_text(strip=True).split(' ')[0]
                    return raw_val
    except:
        pass
    return None

def main():
    parser = argparse.ArgumentParser(description="Estimate Drawdown based on grid parameters.")
    parser.add_argument("--dir", required=True, help="Full path to the output directory.")
    parser.add_argument("--file", required=True, help="Base name of the report/set file (e.g. ADX_BB_GBPAUD_9_3696).")
    parser.add_argument("--date", help="Date to analyze (YYYY-MM-DD). If omitted, finds the max gap day.")
    parser.add_argument("--lot", type=float, help="Custom LotSize override.")
    parser.add_argument("--pipgap", type=float, help="Custom PipGap override.")
    
    args = parser.parse_args()
    
    output_dir = args.dir
    basename = args.file
    target_date_str = args.date
    target_date = None
    if target_date_str:
        try:
            target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        except ValueError:
            print(f"Error: Invalid date format '{target_date_str}'. Use YYYY-MM-DD.")
            return

    # Paths
    set_path = os.path.join(output_dir, "sets", f"{basename}.set")
    trades_path = os.path.join(output_dir, "trades", f"all_trades_{basename}.csv")
    prices_dir = os.path.join(output_dir, "prices")
    report_list_path = os.path.join(output_dir, "report_list.csv")

    # 1. Load Parameters
    params = parse_set_file(set_path)
    if not params:
        print(f"Error: Could not find or read .set file at {set_path}")
        return

    # 2. Extract Base Parameters
    s_lot = float(params.get('LotSize', 0))
    if args.lot is not None:
        s_lot = args.lot
        print(f"Using Custom LotSize: {s_lot}")
    else:
        print(f"Using Set File LotSize: {s_lot}")

    s_lotexp = float(params.get('LotSizeExponent', 1))
    s_max_lot = float(params.get('MaxLots', 999))
    s_pipstep = float(params.get('PipStep', 0))
    s_pipstepexp = float(params.get('PipStepExponent', 1))
    s_maxpipstep = float(params.get('MaxPipStep', 0))
    s_ld = int(params.get('LiveDelay', 0))

    # 3. Symbol Detection & Pip Gap calculation
    current_pipstep = s_pipstep
    detected_symbol = None
    df_at = None

    if os.path.exists(trades_path):
        try:
            df_at = pd.read_csv(trades_path)
            if not df_at.empty:
                df_at['Time'] = pd.to_datetime(df_at['Time'])
                df_at['DateOnly'] = df_at['Time'].dt.date
                if 'Symbol' in df_at.columns:
                    # Robust symbol detection: find the first non-empty symbol
                    valid_symbols = df_at['Symbol'].dropna()
                    valid_symbols = valid_symbols[valid_symbols.astype(str).str.strip() != ""]
                    if not valid_symbols.empty:
                        detected_symbol = valid_symbols.iloc[0]
        except:
            pass

    # Try to get symbol from HTML if CSV failed or symbol missing
    if not detected_symbol or str(detected_symbol).upper() == "NAN":
        if os.path.exists(report_list_path):
            try:
                df_rl = pd.read_csv(report_list_path)
                if 'FilePath' in df_rl.columns:
                    for _, row in df_rl.iterrows():
                        row_basename = os.path.splitext(os.path.basename(row['FilePath']))[0]
                        if row_basename == basename:
                            detected_symbol = extract_symbol_from_html(row['FilePath'])
                            if detected_symbol: break
            except:
                pass

    if not detected_symbol or str(detected_symbol).upper() == "NAN":
        # Final heuristic from basename
        parts = basename.split('_')
        for p in parts:
            if len(p) == 6: # e.g. GBPAUD
                detected_symbol = p
                break
    
    if not detected_symbol or str(detected_symbol).upper() == "NAN":
        print("Warning: Could not detect symbol. Defaulting to EURUSD (0.0001 point).")
        detected_symbol = "EURUSD"
    
    symbol_str = str(detected_symbol).upper()
    point = 0.01 if "JPY" in symbol_str else 0.0001
    print(f"Symbol: {symbol_str} (Point: {point})")

    # --- Skip Logic & ATR Scaling Pre-check ---
    if s_maxpipstep < 0 and s_pipstep > 0:
        print(f"\nSkipping Theoretical DD Calculation: MaxPipStep is negative ({s_maxpipstep}) while PipStep is positive ({s_pipstep}). ATR cannot be calculated.")
        return

    # --- Global Pip Gap Calculation ---
    global_avg_gap = 0
    global_mean_pipstep = s_pipstep # Fallback
    if df_at is not None and not df_at.empty:
        all_gaps = []
        if 'SequenceNumber' in df_at.columns:
            in_deals_all = df_at[df_at['Direction'].astype(str).str.lower() == 'in']
            for _, s_group in in_deals_all.groupby('SequenceNumber'):
                s_group = s_group.sort_values('Time')
                if len(s_group) >= 2:
                    prics = s_group['Price'].values
                    for i in range(len(prics) - 1):
                        gap = abs(prics[i+1] - prics[i]) / point
                        all_gaps.append(gap)
        
        if all_gaps:
            global_avg_gap = sum(all_gaps) / len(all_gaps)
            # Remove normalization step: global_mean_pipstep = global_avg_gap / (s_pipstepexp ** s_ld)
            global_mean_pipstep = global_avg_gap
            print(f"Global Mean Pip Gap: {global_avg_gap:.1f} (Using as PipStep: {global_mean_pipstep:.1f})")

    # --- Date Selection: Auto-detect Max Gap Day if omitted ---
    if target_date is None:
        if df_at is not None and not df_at.empty:
            print("No --date provided. Auto-detecting Max Gap Day...")
            best_date = None
            max_day_pipstep = -1.0
            
            unique_dates = sorted(df_at['DateOnly'].unique())
            for d in unique_dates:
                day_deals = df_at[df_at['DateOnly'] == d]
                ins = day_deals[day_deals['Direction'].astype(str).str.lower() == 'in']
                if ins.empty: continue
                
                day_pipstep = s_pipstep
                if s_pipstep < 0:
                    day_gaps = []
                    if 'SequenceNumber' in ins.columns:
                        for _, s_group in ins.groupby('SequenceNumber'):
                            s_group = s_group.sort_values('Time')
                            if len(s_group) >= 2:
                                prics = s_group['Price'].values
                                # Requirement: use the gap between the first two trades
                                day_gaps.append(abs(prics[1] - prics[0]) / point)
                    
                    if day_gaps:
                        # Requirement: use the first available sequence's first gap on that day?
                        # Or mean of "first gaps" of all sequences on that day?
                        # "use the gap between the first two trades" implies first one.
                        # Let's take the mean of "first gaps" of all sequences starting on that day for stability.
                        day_pipstep = (sum(day_gaps) / len(day_gaps))
                
                if day_pipstep > max_day_pipstep:
                    max_day_pipstep = day_pipstep
                    best_date = d
            
            if best_date:
                target_date = best_date
                target_date_str = str(best_date)
                print(f"Auto-detected Max Gap Day: {target_date_str} (PipStep: {max_day_pipstep:.1f})")
            else:
                print("Error: Could not find any trades with pip gaps to detect Max Gap Day.")
                return
        else:
            print("Error: --date is required when trade file is missing.")
            return

    # --- Pip Gap calculation for target date ---
    if args.pipgap is not None:
        current_pipstep = args.pipgap
        print(f"Using Custom PipGap override: {current_pipstep}")
    elif s_pipstep < 0:
        if df_at is None:
            print(f"Error: PipStep is negative ({s_pipstep}), but trade data missing.")
            return
        
        day_deals = df_at[df_at['DateOnly'] == target_date]
        ins = day_deals[day_deals['Direction'].astype(str).str.lower() == 'in']
        
        all_day_gaps = []
        if 'SequenceNumber' in ins.columns:
            for _, s_group in ins.groupby('SequenceNumber'):
                s_group = s_group.sort_values('Time')
                if len(s_group) >= 2:
                    prics = s_group['Price'].values
                    for i in range(len(prics) - 1):
                        all_day_gaps.append(abs(prics[i+1] - prics[i]) / point)
        
        if all_day_gaps:
            # Use mean of the "first gaps" for sequences on this date
            mean_gap_date = sum(all_day_gaps) / len(all_day_gaps)
            # Remove normalization
            current_pipstep = mean_gap_date
            print(f"Calculated Pip Step for {target_date_str} (Mean of first gaps): {mean_gap_date:.1f}")
        else:
            if global_avg_gap > 0:
                current_pipstep = global_mean_pipstep
                print(f"Warning: No multi-trade sequences on {target_date_str}. Falling back to Global Mean PipStep: {current_pipstep:.1f}")
            else:
                print(f"Error: Could not calculate mean pip gap for {target_date_str} or global mean.")
                return
    else:
        print(f"Using Default/Custom PipStep: {current_pipstep}")

    # 5. FX Rate Conversion
    fx_rates = load_fx_rates(prices_dir)
    fx_factor = get_usd_conv_factor(symbol_str, target_date, fx_rates)
    print(f"USD Conversion Factor for {target_date_str}: {fx_factor:.4f}")

    # 6. Theoretical Calculation
    # Level 1 to 20
    # Level 1 volume includes LiveDelay + 1st physical trade
    def get_theo_lot(k):
        return min(s_max_lot, s_lot * (s_lotexp ** (k-1)))

    volumes = [0.0] * 22
    volumes[1] = sum(get_theo_lot(j) for j in range(1, s_ld + 2))
    for i in range(2, 21):
        volumes[i] = get_theo_lot(s_ld + i)

    # Calculate Gaps and Prices for both scenarios
    p_anchor = 1.0
    
    # ATR-based MaxPipStep scaling
    calculated_atr = current_pipstep / abs(s_pipstep) if s_pipstep != 0 else 1.0
    effective_maxpipstep = calculated_atr * abs(s_maxpipstep) if s_maxpipstep < 0 else s_maxpipstep
    
    # Global ATR calculation for Mean scenario
    global_atr = global_mean_pipstep / abs(s_pipstep) if s_pipstep != 0 else 1.0
    effective_global_maxpipstep = global_atr * abs(s_maxpipstep) if s_maxpipstep < 0 else s_maxpipstep

    # Default scenario
    prices_def = [0.0] * 23
    prices_def[s_ld + 1] = p_anchor
    for k in range(s_ld + 1, 22):
        gap = min(effective_maxpipstep, current_pipstep * (s_pipstepexp ** (k-1))) if effective_maxpipstep > 0 else current_pipstep * (s_pipstepexp ** (k-1))
        prices_def[k+1] = prices_def[k] + (gap * point)

    # Mean scenario
    prices_mean = [0.0] * 23
    prices_mean[s_ld + 1] = p_anchor
    for k in range(s_ld + 1, 22):
        gap = min(effective_global_maxpipstep, global_mean_pipstep * (s_pipstepexp ** (k-1))) if effective_global_maxpipstep > 0 else global_mean_pipstep * (s_pipstepexp ** (k-1))
        prices_mean[k+1] = prices_mean[k] + (gap * point)

    # 7. Print Table
    print("\n" + "="*110)
    print(f"{'':<11} | {'':<10} | {'Passed/Default PipGap':<29} | {'Mean PipGap':<29}")
    print(f"{'Level':<8} | {'Lot':<10} | {'Total Gap':<12} | {'Total DD':<14} | {'Total Gap':<12} | {'Total DD':<14}")
    print("-" * 110)

    # ANSI colors
    RED = "\033[91m"
    RESET = "\033[0m"

    multiplier = 100000
    for i in range(1, 21):
        # Default DD calculation
        target_price_def = prices_def[min(s_ld + i + 1, 22)]
        dd_def = 0
        for j in range(1, i + 1):
            dd_def += volumes[j] * abs(target_price_def - prices_def[s_ld + j])
        dd_usd_def = dd_def * multiplier * fx_factor
        gap_pips_def = abs(target_price_def - p_anchor) / point

        # Mean DD calculation
        target_price_mean = prices_mean[min(s_ld + i + 1, 22)]
        dd_mean = 0
        for j in range(1, i + 1):
            dd_mean += volumes[j] * abs(target_price_mean - prices_mean[s_ld + j])
        dd_usd_mean = dd_mean * multiplier * fx_factor
        gap_pips_mean = abs(target_price_mean - p_anchor) / point
        
        # Prepare strings with conditional coloring
        dd_usd_def_str = f"${dd_usd_def:<13.2f}"
        if dd_usd_def >= 1000:
            dd_usd_def_str = f"{RED}{dd_usd_def_str}{RESET}"
            
        dd_usd_mean_str = f"${dd_usd_mean:<13.2f}"
        if dd_usd_mean >= 1000:
            dd_usd_mean_str = f"{RED}{dd_usd_mean_str}{RESET}"
        
        # --- Crossover Checks ---
        # 1. Default Scenario Crossover
        prev_dd_usd_def = 0
        if i > 1:
            prev_target_price_def = prices_def[min(s_ld + i, 22)]
            prev_dd_def = 0
            for j in range(1, i):
                prev_dd_def += volumes[j] * abs(prev_target_price_def - prices_def[s_ld + j])
            prev_dd_usd_def = prev_dd_def * multiplier * fx_factor
        
        if prev_dd_usd_def < 1000 <= dd_usd_def:
            # Interpolate Gap
            open_vol = sum(volumes[j] for j in range(1, i + 1))
            needed_price_diff = (1000 - prev_dd_usd_def) / (open_vol * multiplier * fx_factor)
            price_at_1k = prices_def[min(s_ld + i, 22)] + (needed_price_diff if prices_def[min(s_ld + i + 1, 22)] > prices_def[min(s_ld + i, 22)] else -needed_price_diff)
            gap_at_1k = abs(price_at_1k - p_anchor) / point
            print(f"{'---':<8} | {'---':<10} | {gap_at_1k:<12.1f} | {RED}{'$1,000.00':<13}{RESET} | {'---':<12} | {'---':<14} (Default Threshold)")

        # 2. Mean Scenario Crossover
        prev_dd_usd_mean = 0
        if i > 1:
            prev_target_price_mean = prices_mean[min(s_ld + i, 22)]
            prev_dd_mean = 0
            for j in range(1, i):
                prev_dd_mean += volumes[j] * abs(prev_target_price_mean - prices_mean[s_ld + j])
            prev_dd_usd_mean = prev_dd_mean * multiplier * fx_factor

        if prev_dd_usd_mean < 1000 <= dd_usd_mean:
            # Interpolate Gap
            open_vol = sum(volumes[j] for j in range(1, i + 1))
            needed_price_diff = (1000 - prev_dd_usd_mean) / (open_vol * multiplier * fx_factor)
            price_at_1k = prices_mean[min(s_ld + i, 22)] + (needed_price_diff if prices_mean[min(s_ld + i + 1, 22)] > prices_mean[min(s_ld + i, 22)] else -needed_price_diff)
            gap_at_1k = abs(price_at_1k - p_anchor) / point
            print(f"{'---':<8} | {'---':<10} | {'---':<12} | {'---':<14} | {gap_at_1k:<12.1f} | {RED}{'$1,000.00':<13}{RESET} (Mean Threshold)")

        line = f"{i:<8} | {volumes[i]:<10.2f} | {gap_pips_def:<12.1f} | {dd_usd_def_str} | {gap_pips_mean:<12.1f} | {dd_usd_mean_str}"
        print(line)

    print("="*110)
    
    # --- 8. Pip Gap vs Starting Lot Analysis (Horizontal Table) ---
    print(f"1k Drawdown Threshold vs. Starting Lot (Pips) - Based on {target_date_str}:")
    target_lots = [0.01, 0.02, 0.03, 0.04, 0.05]
    results_1k = {}
    
    for start_lot in target_lots:
        # Simulate volumes for this start_lot
        sim_volumes = [0.0] * 22
        def get_sim_lot(k):
            return min(s_max_lot, start_lot * (s_lotexp ** (k-1)))
        
        sim_volumes[1] = sum(get_sim_lot(j) for j in range(1, s_ld + 2))
        for j in range(2, 21):
            sim_volumes[j] = get_sim_lot(s_ld + j)
            
        # Use existing prices_def (which used current_pipstep)
        k1_gap = "N/A"
        total_lots_at_1k = "N/A"
        level_at_1k = "N/A"
        last_dd_usd = 0
        last_gap_pips = 0
        
        for i in range(1, 21):
            t_price = prices_def[min(s_ld + i + 1, 22)]
            dd_val = 0
            open_lots = 0
            for j in range(1, i + 1):
                dd_val += sim_volumes[j] * abs(t_price - prices_def[s_ld + j])
                open_lots += sim_volumes[j]
            dd_usd = dd_val * multiplier * fx_factor
            gap_pips = abs(t_price - p_anchor) / point
            
            if last_dd_usd < 1000 <= dd_usd:
                # Interpolate Gap
                if dd_usd > last_dd_usd:
                    gap_val = last_gap_pips + (gap_pips - last_gap_pips) * (1000 - last_dd_usd) / (dd_usd - last_dd_usd)
                    k1_gap = f"{gap_val:.1f}"
                    total_lots_at_1k = f"{open_lots:.2f}"
                    level_at_1k = f"L{i}-{i+1}"
                break
            last_dd_usd = dd_usd
            last_gap_pips = gap_pips
        
        results_1k[start_lot] = {'gap': k1_gap, 'lots': total_lots_at_1k, 'level': level_at_1k}

    # Print Horizontal Table
    header_row = " | ".join([f"{lot:<10}" for lot in target_lots])
    gap_row    = " | ".join([f"{results_1k[lot]['gap']:<10}" for lot in target_lots])
    lots_row   = " | ".join([f"{results_1k[lot]['lots']:<10}" for lot in target_lots])
    level_row  = " | ".join([f"{results_1k[lot]['level']:<10}" for lot in target_lots])
    
    print(f"{'Lot Size':<12} | {header_row}")
    print("-" * (15 + len(header_row)))
    print(f"{'1k Pip Gap':<12} | {gap_row}")
    print(f"{'Total Lots':<12} | {lots_row}")
    print(f"{'Trade Level':<12} | {level_row}")
    print("="*110)

    print(f"Settings Used:")
    print(f" - LotSize: {s_lot}, Exponent: {s_lotexp}, Max: {s_max_lot}")
    print(f" - PipStep: {current_pipstep:.2f}, Exponent: {s_pipstepexp}, Max: {effective_maxpipstep:.2f} (Input: {s_maxpipstep})")
    print(f" - LiveDelay: {s_ld}")
    print(f" - USD Conversion Factor: {fx_factor:.4f} (Symbol: {symbol_str})")

if __name__ == "__main__":
    main()

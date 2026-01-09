import os
import glob
import pandas as pd
from datetime import datetime
import argparse
import shutil
import re
from bs4 import BeautifulSoup
import yfinance as yf

def generate_file_list():
    parser = argparse.ArgumentParser(description='Generate a CSV file list of .htm reports from a parent folder.')
    parser.add_argument('parent_path', type=str, help='Path to the parent folder containing the "HTML Reports" subfolder.')
    args = parser.parse_args()

    # Get absolute path of the parent folder
    parent_path = os.path.abspath(args.parent_path)
    
    if not os.path.exists(parent_path):
        print(f"Error: Parent folder not found: {parent_path}")
        return

    # Determine the reports folder (always "HTML Reports" under parent_path)
    reports_path = os.path.join(parent_path, "HTML Reports")
        
    if not os.path.exists(reports_path):
        print(f"Error: 'HTML Reports' folder not found under {parent_path}")
        return

    print(f"Scanning reports in: {reports_path}")

    # Find .htm files in the determined reports directory only
    htm_files = glob.glob(os.path.join(reports_path, "*.htm"))
    
    if not htm_files:
        print(f"No .htm files found in {reports_path}")
        return

    # Prepare data for CSV
    data = []
    for f in htm_files:
        data.append({
            'FilePath': os.path.abspath(f),
            'Include': 1
        })

    # Sort by filename for consistency
    data.sort(key=lambda x: os.path.basename(x['FilePath']))

    df = pd.DataFrame(data)

    # Prepare output directory (analysis/output_<timestamp> inside parent_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(parent_path, "analysis", f"output_{timestamp}")
    os.makedirs(output_dir, exist_ok=True)

    output_file = os.path.join(output_dir, "report_list.csv")

    # Save to CSV
    df.to_csv(output_file, index=False)
    
    # Copy .set files to output/sets directory
    sets_dir = os.path.join(output_dir, "sets")
    os.makedirs(sets_dir, exist_ok=True)
    set_files = glob.glob(os.path.join(parent_path, "*.set"))
    for set_file in set_files:
        shutil.copy2(set_file, sets_dir)
    
    print(f"Generated report list with {len(htm_files)} files from {os.path.basename(reports_path)}.")
    if set_files:
        print(f"Copied {len(set_files)} .set files to {sets_dir}")
    print(f"Output folder created: {output_dir}")
    print(f"Report list saved to: {output_file}")

    # Extract period from the first report
    if htm_files:
        first_report = htm_files[0]
        print(f"\nExtracting backtest period from: {first_report}")
        start_date, end_date = extract_period(first_report)
        
        if start_date and end_date:
            print(f"\nExtracted Backtest Period: {start_date} to {end_date}")
            download_fx_data(output_dir, start_date, end_date)
        else:
            print("\nCould not extract backtest period from the report.")

def extract_period(html_file):
    """Extracts start and end dates from the MetaTrader HTML report."""
    try:
        # Try reading with different encodings
        content = None
        for encoding in ['utf-16', 'utf-8', 'cp1252']:
            try:
                with open(html_file, 'r', encoding=encoding, errors='ignore') as f:
                    content = f.read()
                if content and len(content) > 100:
                    break
            except Exception:
                continue
        
        if not content:
            print(f"  Warning: Could not read content from {html_file}")
            return None, None

        soup = BeautifulSoup(content, 'lxml')
        all_text = soup.get_text(separator=' ', strip=True)
        
        # Use a more flexible regex to find the period. 
        # MT5 reports usually have "Period: [Timeframe] (YYYY.MM.DD - YYYY.MM.DD)"
        # We look for "Period:" followed by any characters until the parentheses part
        pattern = r'Period:.*?\((\d{4}\.\d{2}\.\d{2})\s*-\s*(\d{4}\.\d{2}\.\d{2})\)'
        match = re.search(pattern, all_text, re.IGNORECASE | re.DOTALL)
        
        if match:
            start_date = match.group(1).replace('.', '-')
            end_date = match.group(2).replace('.', '-')
            return start_date, end_date
            
        # Fallback: search for any date range in parentheses if "Period:" wasn't found near it
        # This can happen if the text structure is very fragmented
        pattern_fallback = r'\((\d{4}\.\d{2}\.\d{2})\s*-\s*(\d{4}\.\d{2}\.\d{2})\)'
        matches = re.findall(pattern_fallback, all_text)
        if matches:
            # Usually the first date range in the report is the period
            start_date = matches[0][0].replace('.', '-')
            end_date = matches[0][1].replace('.', '-')
            return start_date, end_date

    except Exception as e:
        print(f"Error extracting period: {e}")
    return None, None

def download_fx_data(output_dir, start_date, end_date):
    """Downloads daily FX close prices for specified pairs."""
    fx_pairs = [
        'EURUSD', 'USDCHF', 'USDJPY', 'USDCAD', 
        'AUDUSD', 'GBPUSD', 'NZDUSD'
    ]
    
    prices_dir = os.path.join(output_dir, "prices")
    os.makedirs(prices_dir, exist_ok=True)
    
    print(f"Downloading daily close price data to: {prices_dir}")
    
    # Increase end_date by 1 day because yfinance end is exclusive
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    from datetime import timedelta
    adjusted_end_date = (end_dt + timedelta(days=1)).strftime("%Y-%m-%d")

    for pair in fx_pairs:
        ticker = f"{pair}=X"
        print(f"  Downloading {pair}...", end="", flush=True)
        try:
            data = yf.download(ticker, start=start_date, end=adjusted_end_date, interval="1d", progress=False)
            if not data.empty:
                # In recent yfinance versions, data might have multi-index columns
                # We extract the 'Close' price and simplify the structure
                if isinstance(data.columns, pd.MultiIndex):
                    data = data['Close']
                else:
                    data = data[['Close']]
                
                # Ensure we have a single column named 'Price' and index as 'Date'
                df_export = pd.DataFrame(data)
                df_export.columns = ['Price']
                df_export.index.name = 'Date'
                
                output_path = os.path.join(prices_dir, f"{pair}.csv")
                df_export.to_csv(output_path)
                print(" Done.")
            else:
                print(" No data found.")
        except Exception as e:
            print(f" Error: {e}")

if __name__ == "__main__":
    generate_file_list()

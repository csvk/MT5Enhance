import os
import argparse
import re
import math
import shutil
from bs4 import BeautifulSoup

def parse_max_trades(html_path):
    """
    Parses Full_Analysis.html and returns a dictionary mapping report basename to Max Trades.
    Handles HTML formatting variations like newlines and extra tags.
    """
    if not os.path.exists(html_path):
        print(f"Error: {html_path} not found.")
        return {}

    with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    soup = BeautifulSoup(content, 'html.parser')
    report_max_trades = {}

    # Find all h3 tags which represent report sections
    sections = soup.find_all('h3')
    for h3 in sections:
        h3_text = h3.get_text(separator=' ', strip=True)
        # Normalize whitespace
        h3_text = ' '.join(h3_text.split())
        
        if 'Report:' not in h3_text:
            continue
        
        # Extract report name (e.g., "1. Report: at_eurchf_5_3972")
        # Try to find link first as it often contains the clean basename
        a_tag = h3.find('a')
        if a_tag:
            report_name = a_tag.get_text(strip=True)
        else:
            report_name = h3_text.split('Report:')[-1].strip()

        # Look for "Max Trades in Sequence" in the list following the h3
        # It's usually in a metrics-list ul
        metrics_list = h3.find_next('ul')
        if metrics_list:
            # Check all li items within the list
            for li in metrics_list.find_all('li'):
                li_text = li.get_text(separator=' ', strip=True)
                li_text = ' '.join(li_text.split()) # Normalize whitespace/newlines
                
                if 'Max Trades in Sequence' in li_text:
                    # Match "Max Trades in Sequence : 6 [2025-01-02]" or "Max Trades in Sequence: 6"
                    match = re.search(r'Max Trades in Sequence[\s:]+(\d+)', li_text, re.IGNORECASE)
                    if match:
                        max_trades = int(match.group(1))
                        report_max_trades[report_name] = max_trades
                        break

    return report_max_trades

    return report_max_trades

def update_set_file(src_path, dst_path, live_delay):
    """
    Copies a set file and updates the LiveDelay parameter.
    """
    try:
        # Detect encoding
        content = None
        for enc in ['utf-16', 'utf-16-le', 'utf-8', 'latin-1', 'cp1252']:
            try:
                with open(src_path, 'r', encoding=enc, errors='ignore') as f:
                    content = f.read()
                    if '=' in content:
                        used_enc = enc
                        break
            except:
                continue
        
        if content is None:
            print(f"Warning: Could not read {src_path}")
            return False

        lines = content.splitlines()
        new_lines = []
        found = False
        for line in lines:
            if '=' in line:
                key = line.split('=')[0].strip()
                if key.lower() == 'livedelay':
                    # MT5 set files might have || after value for comments
                    parts = line.split('||', 1)
                    if len(parts) > 1:
                        new_lines.append(f"LiveDelay={live_delay}||{parts[1]}")
                    else:
                        new_lines.append(f"LiveDelay={live_delay}")
                    found = True
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        
        if not found:
            # If LiveDelay was not in the file, we can optionally add it at the end
            # But usually it should be there.
            new_lines.append(f"LiveDelay={live_delay}")

        with open(dst_path, 'w', encoding=used_enc) as f:
            f.write('\n'.join(new_lines) + '\n')
        return True
    except Exception as e:
        print(f"Error updating {src_path}: {e}")
        return False

def parse_contributors(html_path):
    """
    Parses Full_Analysis.html and returns a set of report basenames found in the 
    'Monthly Contributor Breakdown' table. Robust against whitespace variations.
    """
    if not os.path.exists(html_path):
        return set()

    with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    soup = BeautifulSoup(content, 'html.parser')
    contributors = set()

    # Find the Monthly Contributor Breakdown heading (handle newlines/whitespace)
    pattern = re.compile(r'Monthly\s+Contributor\s+Breakdown', re.IGNORECASE | re.DOTALL)
    heading = soup.find(lambda tag: tag.name in ["h1", "h2", "h3"] and pattern.search(tag.get_text()))
    
    if not heading:
        # Fallback search anywhere
        heading = soup.find(string=pattern)

    if heading:
        # Resolve to the actual tag if 'string' search was used
        if hasattr(heading, 'parent') and heading.parent:
            current = heading.parent
        else:
            current = heading
            
        # The table is likely the next sibling or a sibling after some text
        table = current.find_next('table')
        if table:
            # In analyze.py, the first column is 'Report', but columns might change.
            # We look for the 'Report' header to be precise, or assume column index 2 if 'Report' is not explicit.
            headers = [th.get_text(strip=True).lower() for th in table.find_all('th')]
            report_col_idx = 2 # Default to 3rd column (index 2) where 'Report File' usually is
            for idx, h in enumerate(headers):
                if 'report' in h:
                    report_col_idx = idx
                    break
            
            rows = table.find('tbody').find_all('tr') if table.find('tbody') else table.find_all('tr')[1:]
            for row in rows:
                cols = row.find_all('td')
                if len(cols) > report_col_idx:
                    report_name = cols[report_col_idx].get_text(strip=True)
                    # Normalize: strip extension if present
                    report_name = re.sub(r'\.html?$', '', report_name, flags=re.IGNORECASE)
                    if report_name:
                        contributors.add(report_name)

    return contributors

    return contributors

def main():
    parser = argparse.ArgumentParser(description='Create LiveDelay variations of set files based on Max Trades.')
    parser.add_argument('output_dir', type=str, help='Path to the analysis output directory (e.g., analysis/output_*)')
    parser.add_argument('--limit', '-l', type=int, default=None, help='Max number of ld variations to create (e.g., 2 will only create ld1 and ld2)')
    parser.add_argument('-n', type=int, default=None, help='Generate ONLY the ld<N> variation (e.g., -n 2 will only create ld2)')
    parser.add_argument('--all', action='store_true', help='Generate variations for ALL reports found in the analysis, not just contributors.')
    args = parser.parse_args()

    output_dir = os.path.abspath(args.output_dir)
    html_path = os.path.join(output_dir, "Full_Analysis.html")
    sets_dir = os.path.join(output_dir, "sets")
    ldsets_dir = os.path.join(output_dir, "ldsets")

    if not os.path.exists(html_path):
        print(f"Error: {html_path} not found.")
        return

    if not os.path.exists(sets_dir):
        print(f"Error: Sets directory not found at {sets_dir}")
        return

    # 1. Refresh ldsets folder
    if os.path.exists(ldsets_dir):
        print(f"Refreshing directory: {ldsets_dir}")
        shutil.rmtree(ldsets_dir)
    
    os.makedirs(ldsets_dir, exist_ok=True)
    print(f"Created directory: {ldsets_dir}")

    # 2. Extract Max Trades from report
    report_max_trades = parse_max_trades(html_path)
    print(f"Extracted Max Trades for {len(report_max_trades)} reports.")

    # 3. Filtering logic (Contributors by default)
    if not args.all:
        contributors = parse_contributors(html_path)
        if contributors:
            print(f"Found {len(contributors)} reports in Monthly Contributor Breakdown.")
            
            # Filter report_max_trades to only those in contributors
            # Use case-insensitive matching for robustness
            contributor_lower = {c.lower() for c in contributors}
            filtered_trades = {k: v for k, v in report_max_trades.items() if k.lower() in contributor_lower}
            
            # Robustness: If filtering results in 0 but contributors were found, maybe names differ?
            if len(filtered_trades) == 0 and len(contributors) > 0:
                 print(f"Warning: Contributor names did not match report keys exactly. Processing all found.")
            else:
                 report_max_trades = filtered_trades
                 print(f"Filtered to {len(report_max_trades)} contributor reports.")
        else:
            print("Warning: No 'Monthly Contributor Breakdown' table found. Processing all reports.")
    else:
        print("Flag --all used. Processing all reports.")

    # 4. Process each report
    created_count = 0
    for report_name, max_trades in report_max_trades.items():
        if max_trades > 4:
            natural_max_ld = math.floor(max_trades / 2)
            
            # Determine which LD variations to create
            if args.n is not None:
                if args.n > natural_max_ld:
                    # print(f"Skipping {report_name}: Requested ld{args.n} exceeds calculated max ld{natural_max_ld}")
                    continue
                ld_range = [args.n]
                print(f"Processing {report_name}: Creating single variation ld{args.n}...")
            else:
                max_ld = natural_max_ld
                if args.limit is not None:
                    max_ld = min(max_ld, args.limit)
                ld_range = range(1, max_ld + 1)
                print(f"Processing {report_name}: Max Trades = {max_trades}, Creating {len(ld_range)} variations...")

            # Locate original set file
            src_set_path = os.path.join(sets_dir, f"{report_name}.set")
            if not os.path.exists(src_set_path):
                print(f"  Warning: Original set file not found at {src_set_path}")
                continue

            # 4. Create variations
            for ld in ld_range:
                dst_set_name = f"{report_name}_ld{ld}.set"
                dst_set_path = os.path.join(ldsets_dir, dst_set_name)
                
                if update_set_file(src_set_path, dst_set_path, ld):
                    created_count += 1
        else:
            # print(f"Skipping {report_name}: Max Trades = {max_trades} (<= 4)")
            pass

    print(f"\nDone. Created {created_count} new set files in {ldsets_dir}.")

if __name__ == "__main__":
    main()

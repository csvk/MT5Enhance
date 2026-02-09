import os
import shutil
import argparse
import pandas as pd
import re
import glob

def export_files():
    parser = argparse.ArgumentParser(description='Export and organize files based on Full_Analysis.html report.')
    parser.add_argument('output_folder', type=str, help='Path to the output folder containing Full_Analysis.html and report_list.csv')
    parser.add_argument('magic_start', type=int, help='Starting magic number for the exported sets')
    args = parser.parse_args()

    output_dir = os.path.abspath(args.output_folder)
    full_analysis_path = os.path.join(output_dir, "Full_Analysis.html")
    report_list_path = os.path.join(output_dir, "report_list.csv")

    if not os.path.exists(full_analysis_path):
        print(f"Error: Full_Analysis.html not found in {output_dir}")
        return
    if not os.path.exists(report_list_path):
        print(f"Error: report_list.csv not found in {output_dir}")
        return

    # 1. Refresh 'export' folder inside output_dir
    selected_dir = os.path.join(output_dir, "export")
    if os.path.exists(selected_dir):
        print(f"Refreshing 'export' folder: {selected_dir}")
        shutil.rmtree(selected_dir)
    os.makedirs(selected_dir, exist_ok=True)

    # 2. Create subfolders
    csv_out_dir = os.path.join(selected_dir, "CSV")
    html_out_dir = os.path.join(selected_dir, "HTML Reports")
    sets_out_dir = os.path.join(selected_dir, "sets")
    os.makedirs(csv_out_dir, exist_ok=True)
    os.makedirs(html_out_dir, exist_ok=True)
    os.makedirs(sets_out_dir, exist_ok=True)

    # 3. Read report_list.csv for original paths
    df_list = pd.read_csv(report_list_path)
    path_map = {os.path.basename(row['FilePath']): row['FilePath'] for _, row in df_list.iterrows()}

    # 4. Parse Full_Analysis.html for reports in the Monthly Contributor Breakdown
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("Error: BeautifulSoup (bs4) is required. Install it with: pip install beautifulsoup4")
        return

    with open(full_analysis_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Extract the table section for Monthly Contributor Breakdown
    h2_contributor = soup.find(['h2', 'h3'], string=lambda t: t and 'Monthly Contributor Breakdown' in t)
    if not h2_contributor:
        # Fallback for slightly different header text
        h2_contributor = soup.find(lambda tag: tag.name in ['h2', 'h3'] and 'Monthly Contributor Breakdown' in tag.get_text())
    
    if not h2_contributor:
        print("Error: Could not find Monthly Contributor Breakdown section in Full_Analysis.html")
        return

    table = h2_contributor.find_next('table')
    if not table:
        print("Error: Could not find table after Monthly Contributor Breakdown header.")
        return

    selected_files = []
    seen = set()
    
    # Extract Max Trades in Sequence mapping
    max_trades_map = {}
    for h3 in soup.find_all('h3'):
        h3_text = h3.get_text()
        if "Report:" in h3_text:
            # Extract filename from <code> tag inside h3 if it exists, or from link
            name_tag = h3.find('code')
            if not name_tag:
                name_tag = h3.find('a')
            
            if name_tag:
                name = name_tag.get_text(strip=True)
                # Use base name for mapping key to avoid extension mismatch
                name_base = os.path.splitext(name)[0]
                ul = h3.find_next_sibling('ul', class_='metrics-list')
                if ul:
                    mt_li = ul.find(lambda tag: tag.name == 'li' and 'Max Trades in Sequence' in tag.get_text())
                    if mt_li:
                        val_text = mt_li.get_text().split(':')[-1].strip()
                        val = val_text.split('[')[0].strip()
                        max_trades_map[name_base] = val

    rows = table.find_all('tr')[1:] # Skip header row
    for row in rows:
        cols = row.find_all('td')
        if len(cols) < 3: continue
        
        # Check if this is a Total row (skip it)
        row_text = row.get_text()
        if "Total" in row_text:
            continue
            
        # The filename is in the 3rd column (index 2)
        report_file_td = cols[2]
        # It's usually inside a <code> tag, possibly within an <a> tag
        code_tag = report_file_td.find('code')
        if code_tag:
            name = code_tag.get_text(strip=True)
            if name in path_map and name not in seen:
                selected_files.append(name)
                seen.add(name)

    if not selected_files:
        print("No report files found in the Monthly Contributor Breakdown table.")
        return

    print(f"Found {len(selected_files)} reports to process.")

    # 5. Copy and modify files
    sets_in_dir = os.path.join(output_dir, "sets")
    magic_counter = args.magic_start
    
    for file_name in selected_files:
        original_htm_path = path_map[file_name]
        base_name = os.path.splitext(file_name)[0]
        
        # a. Copy and modify .set file from output/sets/
        set_file_name = f"{base_name}.set"
        set_in_path = os.path.join(sets_in_dir, set_file_name)
        if os.path.exists(set_in_path):
            set_out_path = os.path.join(sets_out_dir, set_file_name)
            
            # Detect encoding and read content
            encoding_to_use = 'utf-8' # Default
            try:
                with open(set_in_path, 'rb') as rb:
                    raw_bytes = rb.read(4)
                    if raw_bytes.startswith(b'\xff\xfe') or raw_bytes.startswith(b'\xfe\xff'):
                        encoding_to_use = 'utf-16'
                    elif raw_bytes.startswith(b'\xef\xbb\xbf'):
                        encoding_to_use = 'utf-8-sig'
                    else:
                        # Try utf-8 first (stricter than cp1252)
                        try:
                            with open(set_in_path, 'r', encoding='utf-8') as f:
                                f.read()
                            encoding_to_use = 'utf-8'
                        except UnicodeDecodeError:
                            encoding_to_use = 'cp1252'
                
                with open(set_in_path, 'r', encoding=encoding_to_use) as f:
                    content = f.read()
            except Exception as e:
                print(f"  Error: Could not decode {set_file_name}: {e}")
                continue

            # Update Magic Number
            # The format is MAGIC_NUMBER=1||777||1||7770||N
            # We want to replace the first number (before the first ||)
            # If MAGIC_NUMBER is not 0, then do not update it, if it is 0, then use the generated MAGIC_NUMBER.
            pattern = r'(MAGIC_NUMBER=)(\d+)(\|\|.*)'
            match = re.search(pattern, content)
            
            magic_number_updated = False
            if match:
                current_magic = match.group(2)
                if current_magic == "0":
                    new_content = re.sub(pattern, rf'\g<1>{magic_counter}\g<3>', content)
                    magic_number_updated = True
                else:
                    new_content = content
            else:
                new_content = content
            
            # Process TradeComment
            def modify_comment(match):
                prefix = match.group(1) # 'TradeComment='
                val = match.group(2)    # 'range_ema_adx_bb_gbpcad_1_10707'
                suffix = match.group(3) or "" # '||0||...'
                parts = val.split('_')
                if len(parts) >= 4:
                    first_part = parts[0]
                    # Logic: currency is 3rd word from the end.
                    # index: len-3
                    # Keep everything from there onwards.
                    currency_index = len(parts) - 3
                    new_val = first_part + "_" + "_".join(parts[currency_index:])
                    
                    # Add Max Trades Suffix
                    # Use base_name which is already defined as os.path.splitext(file_name)[0]
                    max_val = max_trades_map.get(base_name, "N/A")
                    new_val += f"_Max{max_val}"
                    
                    return f"{prefix}{new_val}{suffix}"
                return match.group(0)

            # Use MULTILINE and restrict to single line to avoid matching across lines
            comment_pattern = r'^(TradeComment=)([^|\r\n]+)(\|\|.*)?$'
            new_content = re.sub(comment_pattern, modify_comment, new_content, flags=re.MULTILINE)
            
            # Write back in the same encoding
            with open(set_out_path, 'w', encoding=encoding_to_use) as f:
                f.write(new_content)
                
            print(f"  Processed: {set_file_name} -> export/sets/ (Magic Number: {magic_counter if magic_number_updated else current_magic if match else 'N/A'}, Max Trades: {max_trades_map.get(base_name, 'N/A')})")
            if magic_number_updated:
                magic_counter += 1
        else:
            print(f"  Warning: .set file not found: {set_in_path}")

        # b. Copy .htm file to HTML Reports/
        if os.path.exists(original_htm_path):
            shutil.copy2(original_htm_path, html_out_dir)
            print(f"  Copied: {file_name} -> export/HTML Reports/")
        else:
            print(f"  Warning: .htm file not found: {original_htm_path}")

        # c. Copy .parquet file to CSV/
        # Logic from analyze.py: sibling CSV folder
        htm_dir = os.path.dirname(original_htm_path)
        csv_in_folder = os.path.join(os.path.dirname(htm_dir), "CSV")
        if os.path.exists(csv_in_folder):
            parquet_pattern = os.path.join(csv_in_folder, f"{base_name}.parquet")
            matches = glob.glob(parquet_pattern)
            if matches:
                for match in matches:
                    shutil.copy2(match, csv_out_dir)
                    print(f"  Copied: {os.path.basename(match)} -> export/CSV/")
            else:
                print(f"  Info: No parquet found for {base_name}")
        else:
            print(f"  Info: CSV folder not found at {csv_in_folder}")

    print(f"\nSelection complete. Files are organized in: {selected_dir}")

if __name__ == "__main__":
    export_files()

import os
import shutil
import argparse
import pandas as pd
import re
import glob

def select_files():
    parser = argparse.ArgumentParser(description='Select and organize files based on Full_Analysis.html report.')
    parser.add_argument('output_folder', type=str, help='Path to the output folder containing Full_Analysis.html and report_list.csv')
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

    # 1. Refresh 'selected' folder inside output_dir
    selected_dir = os.path.join(output_dir, "selected")
    if os.path.exists(selected_dir):
        print(f"Refreshing 'selected' folder: {selected_dir}")
        shutil.rmtree(selected_dir)
    os.makedirs(selected_dir, exist_ok=True)

    # 2. Create subfolders
    csv_out_dir = os.path.join(selected_dir, "CSV")
    html_out_dir = os.path.join(selected_dir, "HTML")
    sets_out_dir = os.path.join(selected_dir, "sets")
    os.makedirs(csv_out_dir, exist_ok=True)
    os.makedirs(html_out_dir, exist_ok=True)
    os.makedirs(sets_out_dir, exist_ok=True)

    # 3. Read report_list.csv for original paths
    df_list = pd.read_csv(report_list_path)
    path_map = {os.path.basename(row['FilePath']): row['FilePath'] for _, row in df_list.iterrows()}

    # 4. Parse Full_Analysis.html for reports in the Monthly Contributor Breakdown
    with open(full_analysis_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    # Extract the table section for Monthly Contributor Breakdown
    # It starts after <h2>Monthly Contributor Breakdown</h2> and ends before the next <h2> or </table>
    table_match = re.search(r'<h2>Monthly Contributor Breakdown</h2>.*?<table>(.*?)</table>', html_content, re.DOTALL)
    if not table_match:
        print("Error: Could not find Monthly Contributor Breakdown table in Full_Analysis.html")
        return

    table_content = table_match.group(1)
    # Find all file names inside <code> tags within the table rows (excluding the header/total rows if they somehow match)
    # The filenames are typically in the 3rd column
    file_names = re.findall(r'<code>(.*?)</code>', table_content)
    
    # Filter out potential duplicates and ensure they exist in our path_map
    selected_files = []
    seen = set()
    for name in file_names:
        if name in path_map and name not in seen:
            selected_files.append(name)
            seen.add(name)

    if not selected_files:
        print("No report files found in the Monthly Contributor Breakdown table.")
        return

    print(f"Found {len(selected_files)} reports to process.")

    # 5. Copy and modify files
    sets_in_dir = os.path.join(output_dir, "sets")
    magic_counter = 1
    
    for file_name in selected_files:
        original_htm_path = path_map[file_name]
        base_name = os.path.splitext(file_name)[0]
        
        # a. Copy and modify .set file from output/sets/
        set_file_name = f"{base_name}.set"
        set_in_path = os.path.join(sets_in_dir, set_file_name)
        if os.path.exists(set_in_path):
            set_out_path = os.path.join(sets_out_dir, set_file_name)
            
            content = None
            # Try different encodings
            for enc in ['utf-16', 'utf-16-le', 'utf-8', 'cp1252']:
                try:
                    with open(set_in_path, 'r', encoding=enc) as f:
                        content = f.read()
                    break
                except (UnicodeDecodeError, UnicodeError):
                    continue
            
            if content is None:
                print(f"  Error: Could not decode {set_file_name} with supported encodings.")
                continue

            # The format is MAGIC_NUMBER=1||777||1||7770||N
            # We want to replace the first number (before the first ||)
            pattern = r'(MAGIC_NUMBER=)(\d+)(\|\|.*)'
            new_content = re.sub(pattern, rf'\g<1>{magic_counter}\g<3>', content)
            
            # Write back in UTF-8 for consistency or keep original? 
            # Usually UTF-8 is safer for modern tools, but MT might expect what it had.
            # Let's write in UTF-8 as it's more universal and shouldn't break MT.
            with open(set_out_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
                
            print(f"  Processed: {set_file_name} -> selected/sets/ (Magic Number: {magic_counter})")
            magic_counter += 1
        else:
            print(f"  Warning: .set file not found: {set_in_path}")

        # b. Copy .htm file to HTML/
        if os.path.exists(original_htm_path):
            shutil.copy2(original_htm_path, html_out_dir)
            print(f"  Copied: {file_name} -> selected/HTML/")
        else:
            print(f"  Warning: .htm file not found: {original_htm_path}")

        # c. Copy .parquet file to CSV/
        # Logic from analyze.py: sibling CSV folder
        htm_dir = os.path.dirname(original_htm_path)
        csv_in_folder = os.path.join(os.path.dirname(htm_dir), "CSV")
        if os.path.exists(csv_in_folder):
            parquet_pattern = os.path.join(csv_in_folder, f"{base_name}*.parquet")
            matches = glob.glob(parquet_pattern)
            if matches:
                for match in matches:
                    shutil.copy2(match, csv_out_dir)
                    print(f"  Copied: {os.path.basename(match)} -> selected/CSV/")
            else:
                print(f"  Info: No parquet found for {base_name}")
        else:
            print(f"  Info: CSV folder not found at {csv_in_folder}")

    print(f"\nSelection complete. Files are organized in: {selected_dir}")

if __name__ == "__main__":
    select_files()

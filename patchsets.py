import os
import sys
import argparse
import re
import subprocess
import pandas as pd
from datetime import datetime

def detect_encoding(file_path):
    """Detect encoding of a file (UTF-16, UTF-8-SIG, or local default)."""
    try:
        with open(file_path, 'rb') as rb:
            raw_bytes = rb.read(4)
            if raw_bytes.startswith(b'\xff\xfe') or raw_bytes.startswith(b'\xfe\xff'):
                return 'utf-16'
            elif raw_bytes.startswith(b'\xef\xbb\xbf'):
                return 'utf-8-sig'
            else:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        f.read()
                    return 'utf-8'
                except UnicodeDecodeError:
                    return 'cp1252'
    except Exception:
        return 'utf-8'

def run_sets2csv(directory, suffix=None):
    """Run sets2csv.py and return the generated CSV path."""
    print(f"Running sets2csv.py on {directory}...")
    # Get initial files in directory to identify the newly created CSV
    initial_files = set(os.listdir(directory))
    
    try:
        result = subprocess.run([sys.executable, 'sets2csv.py', directory], capture_output=True, text=True, check=True)
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error running sets2csv.py: {e.stderr}")
        sys.exit(1)
        
    final_files = set(os.listdir(directory))
    new_files = list(final_files - initial_files)
    
    csv_files = [f for f in new_files if f.startswith('all_sets_set_') and f.endswith('.csv')]
    if not csv_files:
        print("Error: Could not find generated CSV from sets2csv.py")
        sys.exit(1)
    
    original_path = os.path.join(directory, csv_files[0])
    if suffix:
        new_filename = csv_files[0].replace('.csv', f'_{suffix}.csv')
        new_path = os.path.join(directory, new_filename)
        if os.path.exists(new_path):
            os.remove(new_path)
        os.rename(original_path, new_path)
        return new_path
        
    return original_path

def patch_sets(directory, param, target, reset):
    files = [f for f in os.listdir(directory) if f.lower().endswith('.set') and os.path.isfile(os.path.join(directory, f))]
    
    modified_files = []
    
    for file_name in files:
        file_path = os.path.join(directory, file_name)
        encoding = detect_encoding(file_path)
        
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading {file_name}: {e}")
            continue

        # Look for the parameter
        # Pattern: ^Param=Value||Comment
        # We need to match exactly target value
        pattern = rf'^({re.escape(param)}=){re.escape(target)}((\||$|\s).*)$'
        
        new_content, count = re.subn(pattern, rf'\g<1>{reset}\g<2>', content, flags=re.MULTILINE)
        
        if count > 0:
            try:
                with open(file_path, 'w', encoding=encoding) as f:
                    f.write(new_content)
                modified_files.append(file_name)
                print(f"Modified {file_name}: {param} {target} -> {reset}")
            except Exception as e:
                print(f"Error writing to {file_name}: {e}")
                
    return modified_files

def compare_reports(before_csv, after_csv, param, target, reset, modified_files, error_log_path, report_log_path):
    df_before = pd.read_csv(before_csv)
    df_after = pd.read_csv(after_csv)
    
    # Ensure they have the same structure
    if not (df_before.columns.equals(df_after.columns)):
        error_msg = f"Error: CSV headers mismatch between before and after reports."
        with open(error_log_path, 'w') as f:
            f.write(error_msg + '\n')
        print(error_msg)
        return False

    errors = []
    report_data = []
    
    # Filename should be the first column
    for index, row_before in df_before.iterrows():
        filename = row_before['Filename']
        row_after = df_after[df_after['Filename'] == filename].iloc[0]
        
        val_before = "N/A"
        val_after = "N/A"
        
        if param in df_before.columns:
            val_before = str(row_before[param])
            val_after = str(row_after[param])
        
        status = "unchanged"
        if filename in modified_files:
            status = "changed"
            
        report_data.append({
            'Filename': filename,
            'Before': val_before,
            'After': val_after,
            'Status': status
        })

        for col in df_before.columns:
            if col == 'Filename':
                continue
                
            v_b = str(row_before[col])
            v_a = str(row_after[col])
            
            if col == param:
                if filename in modified_files:
                    if v_b == target and v_a == reset:
                        # Correct change
                        pass
                    else:
                        errors.append(f"File {filename}: {param} expected {target}->{reset}, but found {v_b}->{v_a}")
                else:
                    if v_b != v_a:
                        errors.append(f"File {filename}: {param} changed unexpectedly from {v_b} to {v_a} (was not marked as modified)")
            else:
                if v_b != v_a:
                    errors.append(f"File {filename}: Parameter {col} changed unexpectedly from {v_b} to {v_a}")

    # Write report_log.csv
    df_report = pd.DataFrame(report_data)
    df_report.to_csv(report_log_path, index=False)

    if errors:
        # Write patchsets_error_log.csv
        df_errors = pd.DataFrame({'Error': errors})
        df_errors.to_csv(error_log_path, index=False)
        print(f"Error: {len(errors)} unwanted changes detected. See {error_log_path}")
        return False
    
    print(f"Verification successful: Only required changes were made. See {report_log_path}")
    return True

def main():
    parser = argparse.ArgumentParser(description='Batch modify parameters in MT5 .set files.')
    parser.add_argument('--dir', required=True, help='Path to the directory containing .set files')
    parser.add_argument('--param', required=True, help='Parameter name to modify')
    parser.add_argument('--target', required=True, help='Target value to find')
    parser.add_argument('--reset', required=True, help='Value to reset to')
    
    args = parser.parse_args()
    
    directory = os.path.abspath(args.dir)
    if not os.path.isdir(directory):
        print(f"Error: {directory} is not a directory.")
        return

    error_log_path = os.path.join(directory, "patchsets_error_log.csv")
    report_log_path = os.path.join(directory, "report_log.csv")
    
    # 1. Run sets2csv before
    before_csv = run_sets2csv(directory, suffix='before')
    print(f"Before report generated: {before_csv}")
    
    # 2. Patch files
    modified_files = patch_sets(directory, args.param, args.target, args.reset)
    
    if not modified_files:
        print(f"No files matched {args.param}={args.target}. No changes made.")
    
    # 3. Run sets2csv after
    after_csv = run_sets2csv(directory, suffix='after')
    print(f"After report generated: {after_csv}")
    
    # 4. Compare
    success = compare_reports(before_csv, after_csv, args.param, args.target, args.reset, modified_files, error_log_path, report_log_path)
    
    if success:
        # Optionally cleanup temporary CSVs? User might want to keep them.
        pass
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()

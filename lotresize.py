import os
import argparse
import re
import csv

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
                # Try utf-8 first
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        f.read()
                    return 'utf-8'
                except UnicodeDecodeError:
                    return 'cp1252'
    except Exception:
        return 'utf-8'

def lot_resize():
    parser = argparse.ArgumentParser(description='Adjust LotSize in MT5 .set files based on LotSizeExponent.')
    parser.add_argument('directory', type=str, help='Path to the directory containing .set files')
    args = parser.parse_args()

    input_dir = os.path.abspath(args.directory)
    if not os.path.isdir(input_dir):
        print(f"Error: {input_dir} is not a directory.")
        return

    report_path = os.path.join(input_dir, "lotresize_report.csv")
    report_data = []

    files = [f for f in os.listdir(input_dir) if f.lower().endswith('.set') and os.path.isfile(os.path.join(input_dir, f))]

    if not files:
        print(f"No .set files found in {input_dir}")
        return

    for file_name in files:
        file_path = os.path.join(input_dir, file_name)
        encoding = detect_encoding(file_path)
        
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading {file_name}: {e}")
            continue

        # Extract LotSizeExponent and LotSize
        # Format: Key=Value||Comment
        exponent_match = re.search(r'^LotSizeExponent=([\d.]+)', content, re.MULTILINE)
        lotsize_match = re.search(r'^LotSize=([\d.]+)', content, re.MULTILINE)

        if not exponent_match:
            print(f"Skipping {file_name}: LotSizeExponent not found.")
            report_data.append([file_name, "N/A", "N/A", "N/A", "Skipped (Exponent not found)"])
            continue

        exponent_str = exponent_match.group(1)
        try:
            exponent = float(exponent_str)
        except ValueError:
            print(f"Skipping {file_name}: Invalid LotSizeExponent value '{exponent_str}'.")
            report_data.append([file_name, exponent_str, "N/A", "N/A", "Skipped (Invalid Exponent)"])
            continue

        original_lotsize = lotsize_match.group(1) if lotsize_match else "N/A"
        new_lotsize = None

        if exponent == 1.0:
            new_lotsize = "0.03"
        elif exponent == 1.1:
            new_lotsize = "0.02"

        if new_lotsize:
            # Replace LotSize
            if lotsize_match:
                # Replace existing value but keep the rest of the line (|| comments)
                # pattern: ^LotSize=([\d.]+)(.*)$
                content = re.sub(r'^(LotSize=)[\d.]+(.*)$', rf'\g<1>{new_lotsize}\g<2>', content, flags=re.MULTILINE)
            else:
                # Add LotSize if it doesn't exist (though it should)
                content += f"\nLotSize={new_lotsize}"
            
            try:
                with open(file_path, 'w', encoding=encoding) as f:
                    f.write(content)
                print(f"Updated {file_name}: LotSizeExponent={exponent}, LotSize {original_lotsize} -> {new_lotsize}")
                report_data.append([file_name, exponent, original_lotsize, new_lotsize, "Changed"])
            except Exception as e:
                print(f"Error writing to {file_name}: {e}")
                report_data.append([file_name, exponent, original_lotsize, new_lotsize, f"Error: {e}"])
        else:
            print(f"Skipping {file_name}: LotSizeExponent={exponent} (No rule matched)")
            report_data.append([file_name, exponent, original_lotsize, original_lotsize, "Skipped (No rule)"])

    # Write CSV report
    try:
        with open(report_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['FileName', 'LotSizeExponent', 'OriginalLotSize', 'NewLotSize', 'Status'])
            writer.writerows(report_data)
        print(f"\nReport generated: {report_path}")
    except Exception as e:
        print(f"Error writing report: {e}")

if __name__ == "__main__":
    lot_resize()

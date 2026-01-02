import os
import glob
import pandas as pd
from datetime import datetime
import argparse
import shutil

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

if __name__ == "__main__":
    generate_file_list()

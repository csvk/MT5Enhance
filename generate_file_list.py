import os
import glob
import pandas as pd
from datetime import datetime
import argparse

def generate_file_list():
    parser = argparse.ArgumentParser(description='Generate a CSV file list of .htm reports from a folder.')
    parser.add_argument('html_path', type=str, help='Path to the folder containing .htm files.')
    args = parser.parse_args()

    # Get absolute path of the folder
    html_path = os.path.abspath(args.html_path)
    
    if not os.path.exists(html_path):
        print(f"Error: Folder not found: {html_path}")
        return

    # Find .htm files in the top-level directory only
    htm_files = glob.glob(os.path.join(html_path, "*.htm"))
    
    if not htm_files:
        print(f"No .htm files found in {html_path}")
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

    # Prepare output directory (analysis/output_<timestamp> inside html_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(html_path, "analysis", f"output_{timestamp}")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    output_file = os.path.join(output_dir, "report_list.csv")

    # Save to CSV
    df.to_csv(output_file, index=False)
    print(f"Generated report list with {len(htm_files)} files.")
    print(f"Output folder created: {output_dir}")
    print(f"Report list saved to: {output_file}")

if __name__ == "__main__":
    generate_file_list()

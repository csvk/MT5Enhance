# Drawdown Analysis Project

This project provides a 3-step workflow to analyze trading reports. Each analysis run is contained within a dedicated timestamped folder for better organization.

## Project Structure
- `list.py`: Scans a report folder and creates a new `analysis/output_<timestamp>/` directory containing the report list and a `sets/` folder.
- `trades.py`: Processes the reports from Step 1 and saves non-overlapping trades into the same output folder.
- `analyze.py`: Generates charts and a final markdown report inside the same output folder, sourcing parameters from the `sets/` folder.
- `export.py`: (Optional) Extracts and organizes key files (`.set`, `.htm`, `.parquet`) for reports identified in the final analysis.
- `sets2csv.py`: (Utility) Converts a folder of `.set` or `.chr` files into a single `all_sets_<ext>_<timestamp>.csv` with all parameters.

## Expected Directory Structure
```text
[Parent Directory]/
├── File1.set
├── File2.set
├── HTML Reports/
│   ├── File1.htm
│   └── File2.htm
├── analysis/
│   └── output_20231223_120000/        <-- Created in Step 1
│       ├── report_list.csv
│       ├── Portfolio_Overview.png     <-- Created in Step 3
│       ├── Full_Analysis.html         <-- Created in Step 3
│       ├── charts/                    <-- Created in Step 3
│       ├── sets/                      <-- Created in Step 1 (Copy of *.set)
│       ├── Trades/                    <-- Created in Step 2
│       │   ├── all_trades_File1.csv
│       │   ├── selected_trades_SymbolA.csv
│       │   └── selected_trades_SymbolB.csv
│       └── selected/                  <-- Created in Step 4
│           ├── sets/                  <-- Incremental magic numbers
│           │   └── File1.set
│           ├── HTML/
│           │   └── File1.htm
│           └── CSV/
│               └── File1.parquet
└── CSV/                                   <-- Parquet files (optional)
    ├── File1.parquet
    └── File2.parquet
```

## Step-by-Step Instructions

### Step 1: Initialize Analysis
Scan your **parent folder** (the one containing your `HTML Reports` subfolder) to create a new output directory.
```bash
python list.py "C:/Path/To/ParentFolder"
```
*   **Output**: A new folder `analysis/output_YYYYMMDD_HHMMSS/` is created at the parent level.

### Step 2: Extract Trades
Process the reports and extract non-overlapping deal data.
```bash
python trades.py "C:/Path/To/ParentFolder/analysis/output_YYYYMMDD_HHMMSS"
```
*   **Output**: Creates a `Trades/` subfolder inside your output directory.

### Step 3: Portfolio Analysis
Generate performance charts and the final analysis report.
```bash
python analyze.py "C:/Path/To/ParentFolder/analysis/output_YYYYMMDD_HHMMSS"
```
*   **Output**: Saves `Full_Analysis.html` and a `charts/` folder inside the output directory.

### Step 4: Selective Export (Optional)
Extract and organize relevant files for a focused review of the contributors.
```bash
python export.py "C:/Path/To/ParentFolder/analysis/output_YYYYMMDD_HHMMSS"
```
*   **Output**: Creates a `selected/` folder **inside** your output directory with `CSV`, `HTML`, and `sets` subfolders. Each `.set` file is assigned a unique, incremental magic number.

## Utility Scripts

### Export Parameters to CSV
Convert a directory of MT5 `.set` or `.chr` files into a single CSV for easy comparison.
```bash
python sets2csv.py "C:/Path/To/Your/Sets"
```
*   **Auto-Detection**: The script automatically detects the file type in the folder.
*   **Constraint**: The folder must contain only one type of file (`.set` OR `.chr`).
*   **Output**: Generates `all_sets_set_YYYYMMDD_HHMMSS.csv` or `all_sets_chr_YYYYMMDD_HHMMSS.csv` within the same directory.

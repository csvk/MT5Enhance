# Drawdown Analysis Project

This project provides a 3-step workflow to analyze trading reports. Each analysis run is contained within a dedicated timestamped folder for better organization.

## Project Structure
- `list.py`: Scans a report folder and creates a new `analysis/output_<timestamp>/` directory containing the report list.
- `trades.py`: Processes the reports from Step 1 and saves non-overlapping trades into the same output folder.
- `analyze.py`: Generates charts and a final markdown report inside the same output folder.

## Expected Directory Structure
```text
[Parent Directory]/
├── HTML Reports/
│   ├── File1.htm
│   └── File2.htm
├── analysis/
│   └── output_20231223_120000/        <-- Created in Step 1
│       ├── report_list.csv
│       ├── Portfolio_Overview.png     <-- Created in Step 3
│       ├── Full_Analysis.html         <-- Created in Step 3
│       ├── charts/                    <-- Created in Step 3
│       └── Trades/                    <-- Created in Step 2
│           ├── all_trades_File1.csv
│           ├── selected_trades_SymbolA.csv
│           └── selected_trades_SymbolB.csv
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


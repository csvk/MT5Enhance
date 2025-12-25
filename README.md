# Drawdown Analysis Project

This project provides a 3-step workflow to analyze trading reports. Each analysis run is contained within a dedicated timestamped folder for better organization.

## Project Structure
- `generate_file_list.py`: Scans a report folder and creates a new `analysis/output_<timestamp>/` directory containing the report list.
- `generate_trades.py`: Processes the reports from Step 1 and saves non-overlapping trades into the same output folder.
- `analyze_portfolio.py`: Generates charts and a final markdown report inside the same output folder.

## Expected Directory Structure
```text
[Your Report Folder]/
├── File1.htm
├── File2.htm
└── analysis/
    └── output_20231223_120000/        <-- Created in Step 1
        ├── report_list.csv
        ├── Portfolio_Chart.png        <-- Created in Step 3
        ├── Drawdown_Chart.png         <-- Created in Step 3
        ├── Full_Analysis.md           <-- Created in Step 3
        └── Trades/                    <-- Created in Step 2
            ├── selected_trades_SymbolA.csv
            └── selected_trades_SymbolB.csv
```

## Step-by-Step Instructions

### Step 1: Initialize Analysis
Scan your report folder to create a new output directory and selection CSV.
```bash
python generate_file_list.py "C:/Path/To/Reports"
```
*   **Output**: A new folder `analysis/output_YYYYMMDD_HHMMSS/` is created.
*   **Action**: Note the path of this folder; you will need it for the next steps.
*   **Optional**: Edit `report_list.csv` in that folder to exclude specific reports.

### Step 2: Extract Trades
Process the reports and extract non-overlapping deal data into the output folder.
```bash
python generate_trades.py "C:/Path/To/Reports/analysis/output_YYYYMMDD_HHMMSS"
```
*   **Output**: Creates a `Trades/` subfolder inside your output directory.

### Step 3: Portfolio Analysis
Generate performance charts and the final analysis report.
```bash
python analyze_portfolio.py "C:/Path/To/Reports/analysis/output_YYYYMMDD_HHMMSS"
```
*   **Output**: Saves `Portfolio_Chart.png`, `Drawdown_Chart.png`, and `Full_Analysis.md` directly in the output folder.
*   **Custom Date Range**:
    ```bash
    python analyze_portfolio.py "C:/Path/To/Reports/analysis/output_..." --start 2023-11-01 --end 2023-12-31
    ```

## Requirements
- `pandas`
- `matplotlib`
- `beautifulsoup4`
- `lxml`
- `numpy`

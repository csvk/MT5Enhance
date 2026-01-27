# Drawdown Analysis Project

This project provides a 3-step workflow to analyze trading reports. Each analysis run is contained within a dedicated timestamped folder for better organization.

## Project Structure
- `arrange.py`: (Step 0) Organizes files in a `Hunted/` folder into a structured `Hunted/arranged/` directory (HTML Reports, CSV). This creates the parent directory used by subsequent scripts.
- `list.py`: Scans a report folder and creates a new `analysis/output_<timestamp>/` directory containing the report list and a `sets/` folder.
- `trades.py`: Processes the reports from Step 1 and saves non-overlapping trades into the same output folder.
- `analyze.py`: Generates charts and a final markdown report inside the same output folder, sourcing parameters from the `sets/` folder.
- `simulate.py`: Parses the analysis results to create a simplified lot-scaling simulation summary (`sim.html`).
- `compare.py`: Automatically detects and groups strategy variants (e.g., `_t18`, `_ld1`) from `Short_Analysis.html` to produce a side-by-side comparison report (`compare_report.html`).
- `dd.py`: (Utility) Theoretical Drawdown Calculator for analyzing specific reports/days with sensitivity overrides and comparison against mean pip gaps.
- `export.py`: (Optional) Extracts and organizes key files (`.set`, `.htm`, `.parquet`) for reports identified in the final analysis.
- `ldsets.py`: (Utility) Creates `LiveDelay` variations of set files based on "Max Trades in Sequence" results.
- `sets2csv.py`: (Utility) Converts a folder of `.set` or `.chr` files into a single `all_sets_<ext>_<timestamp>.csv` with all parameters.

## Expected Directory Structure
```text
[Parent Directory]/
├── File1.set
├── File2.set
├── HTML Reports/
│   ├── File1.htm
│   └── File2.htm
├── Graphs/
│   └── (remaining .png files)
├── analysis/
│   └── output_20231223_120000/        <-- Created in Step 1
│       ├── report_list.csv
│       ├── prices/                    <-- Created in Step 1 (FX Data)
│       ├── Full_Analysis.html         <-- Created in Step 3
│       ├── Short_Analysis.html        <-- Created in Step 3
│       ├── compare_report.html        <-- Created in Step 6
│       ├── sim.html                   <-- Created in Step 5
│       ├── charts/                    <-- Created in Step 3
│       ├── sets/                      <-- Created in Step 1 (Copy of *.set)
│       ├── ldsets/                    <-- Created by ldsets.py
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

### Step 0: Arrange Files
Organize a raw `Hunted/` folder into a structured format. This script creates the `Hunted/arranged` directory, which serves as the **parent folder** for all subsequent steps.
```bash
python arrange.py "C:/Path/To/DirectoryContainingHunted"
```
*   **Output**: Creates `Hunted/arranged/` with subfolders `HTML Reports`, `CSV`, and `Graphs`.
    *   All `.htm` and `.png` files are copied to `HTML Reports`.
    *   Remaining `.png` files (those not for strategy reports) are additionally copied to `Graphs`.
*   **Next Step**: Use the newly created `arranged` folder path as the input for `list.py`.

### Step 1: Initialize Analysis
Scan your **parent folder** (e.g., `C:/Path/To/Directory/Hunted/arranged`) to create a new output directory. This step also automatically downloads historical daily FX closing prices for required symbols.
```bash
python list.py "C:/Path/To/Directory/Hunted/arranged"
```
*   **Output**: 
    *   A new folder `analysis/output_YYYYMMDD_HHMMSS/` is created.
    *   `report_list.csv`: List of reports to process.
    *   `sets/`: Copy of `.set` files from the parent folder.
    *   `prices/`: Historical FX data (`.csv`) downloaded via `yfinance`.

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
 
### Step 5: Simulation Summary
Generates a consolidated summary report (`sim.html`) showing simulated performance across various fixed lot sizes (0.01 to 0.05).
```bash
python simulate.py "C:/Path/To/ParentFolder/analysis/output_YYYYMMDD_HHMMSS"
```
*   **Output**: Saves `sim.html` inside your output directory and automatically opens it in the browser.
*   **Key Metrics**:
    *   **Max Trades (Seq)**: Shows the longest trade sequence reached, including the start date of that sequence.
    *   **Pip Gap (Max Seq)**: Captures the theoretical "Base Pip Gap" from the analysis for the worst-case scenario.
    *   **Lot Simulations**: Scales PnL and MaxDD linearly for lot sizes 0.01, 0.02, 0.03, 0.04, and 0.05.
    *   **Clickable Links**: Report filenames in the table are clickable links that open the original individual HTML reports.
+
+### Step 6: Variant Comparison
+Automatically groups and compares strategy variations (e.g., different `LiveDelay` or `Timeframe` variants of the same base strategy) found in the `Short_Analysis.html` report.
+```bash
+python compare.py "C:/Path/To/ParentFolder/analysis/output_YYYYMMDD_HHMMSS"
+```
+*   **Output**: Saves `compare_report.html` inside your output directory and automatically opens it in the browser.
+*   **Key Features**:
+    *   **Auto-Detection**: Dynamically finds suffixes like `_ld1`, `_ld2`, `_t18`, etc., to identify variants.
+    *   **Smart Filtering**: Only includes strategies that actually have variants, keeping the report focused.
+    *   **Side-by-Side Comparison**: Displays PnL, Drawdown, Recovery Factor, and Trade Counts for each variant in a clean, comparative table.

## Utility Scripts

### Export Parameters to CSV
Convert a directory of MT5 `.set` or `.chr` files into a single CSV for easy comparison.
```bash
python sets2csv.py "C:/Path/To/Your/Sets"
```
*   **Auto-Detection**: The script automatically detects the file type in the folder.
*   **Constraint**: The folder must contain only one type of file (`.set` OR `.chr`).
*   **Output**: Generates `all_sets_set_YYYYMMDD_HHMMSS.csv` or `all_sets_chr_YYYYMMDD_HHMMSS.csv` within the same directory.

### LiveDelay Variations (`ldsets.py`)
Generates variations of set files with incremental `LiveDelay` values for strategies that reached high sequence levels.
```bash
python ldsets.py "C:/Path/To/analysis/output_folder"
```
*   **Threshold**: Only creates variations if "Max Trades in Sequence" > 4.
*   **Logic**: Creates `floor(Max Trades / 2)` variations (e.g., if Max Trades is 7, creates ld1, ld2, and ld3).
*   **Output**: Saves new `.set` files in an `ldsets/` subfolder.

### Theoretical Drawdown Calculator (`dd.py`)
Provides a detailed console-based sensitivity analysis for individual reports.
```bash
python dd.py --dir "C:/Path/To/output_folder" --file "ReportName" [--date YYYY-MM-DD] [--lot 0.01] [--pipgap 20]
```
*   **Automatic Detection**: If `--date` is omitted, the script automatically identifies the **Max Gap Day** (worst-case volatility day) from the trade history.
*   **Dual Scenario Analysis**: Calculates and displays values for both the "Default/Passed" pip gap and the "Global Mean" pip gap side-by-side.
*   **Sensitivity Overrides**: Use `--lot` and `--pipgap` to test "what-if" scenarios with custom parameters.
*   **Visual Alerts**: Automatically highlights drawdown values exceeding $1,000 in bold red for quick risk assessment.

import os
import sys
import subprocess
import re
import argparse

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ANSI color codes
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"

def log_info(message):
    print(f"{CYAN}{BOLD}[INFO]{RESET} {message}")

def log_success(message):
    print(f"{GREEN}{BOLD}[SUCCESS]{RESET} {message}")

def log_step(message):
    print(f"\n{YELLOW}{BOLD}>>> {message}{RESET}")

def log_error(message):
    print(f"{RED}{BOLD}[ERROR]{RESET} {message}")

def run_command(command, capture_output=False):
    """Runs a shell command and optionally captures its output."""
    try:
        # Use shell=True for Windows compatibility with python commands in some environments, 
        # but list of arguments is generally safer.
        result = subprocess.run(command, capture_output=capture_output, text=True, check=True)
        return result
    except subprocess.CalledProcessError as e:
        log_error(f"Command failed with exit code {e.returncode}")
        if e.stderr:
            print(e.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="End-to-End Analysis Pipeline")
    parser.add_argument("input_path", type=str, help="Path to the parent folder (for initialization) or an existing output folder (to update).")
    parser.add_argument("--all", action="store_true", help="Force analyze.py to process all reports in detail.")
    args = parser.parse_args()

    input_path = os.path.abspath(args.input_path)
    
    if not os.path.exists(input_path):
        log_error(f"Path not found: {input_path}")
        sys.exit(1)

    # Check if this is an existing output directory
    is_output_dir = os.path.exists(os.path.join(input_path, "report_list.csv"))
    
    if is_output_dir:
        log_info(f"Existing output directory detected: {input_path}")
        log_step("Step 1: Skipping step as existing output directory detected")
        output_dir = input_path
    else:
        log_info(f"Starting E2E analysis for parent directory: {input_path}")

        # Step 1: Execute list.py
        log_step("Step 1: Generating report list with list.py")
        list_script = os.path.join(SCRIPT_DIR, "list.py")
        list_cmd = ["python", list_script, input_path]
        log_info(f"Executing: {' '.join(list_cmd)}")
        
        list_result = run_command(list_cmd, capture_output=True)
        print(list_result.stdout)
        
        # Identify output directory from list.py output
        # Pattern: "Output folder created: <path>"
        match = re.search(r"Output folder created:\s*(.*)", list_result.stdout)
        if not match:
            log_error("Could not identify output directory from list.py output.")
            # Fallback: look for the most recent output_* folder in <input_path>/analysis/
            analysis_dir = os.path.join(input_path, "analysis")
            if os.path.exists(analysis_dir):
                subdirs = [os.path.join(analysis_dir, d) for d in os.listdir(analysis_dir) if os.path.isdir(os.path.join(analysis_dir, d)) and d.startswith("output_")]
                if subdirs:
                    output_dir = max(subdirs, key=os.path.getmtime)
                    log_info(f"Fallback: Identified most recent output directory: {output_dir}")
                else:
                    log_error("Fallback failed: No output_* directories found.")
                    sys.exit(1)
            else:
                log_error("Fallback failed: Analysis directory not found.")
                sys.exit(1)
        else:
            output_dir = match.group(1).strip()
            log_success(f"Identified output directory: {output_dir}")

    # Step 2: Execute trades.py
    log_step("Step 2: Extracting trades with trades.py")
    trades_script = os.path.join(SCRIPT_DIR, "trades.py")
    trades_cmd = ["python", trades_script, output_dir]
    if args.all:
        trades_cmd.append("--all")
    log_info(f"Executing: {' '.join(trades_cmd)}")
    run_command(trades_cmd)
    log_success("Trades extraction completed.")

    # Step 3: Execute analyze.py
    log_step("Step 3: Performing portfolio analysis with analyze.py")
    analyze_script = os.path.join(SCRIPT_DIR, "analyze.py")
    analyze_cmd = ["python", analyze_script, output_dir]
    if args.all:
        analyze_cmd.append("--all")
    log_info(f"Executing: {' '.join(analyze_cmd)}")
    run_command(analyze_cmd)
    log_success("Portfolio analysis completed.")

    log_step("Pipeline Execution Successful!")
    log_info(f"Results are available in: {output_dir}")
    full_report = os.path.join(output_dir, "Full_Analysis.html")
    if os.path.exists(full_report):
        log_info(f"Full Report: file:///{full_report.replace(os.sep, '/')}")

if __name__ == "__main__":
    # Enable VT100 Escape Sequence for Windows 10+ CMD
    if os.name == 'nt':
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    
    main()

import pandas as pd
import os
import sys
from datetime import datetime

# Force unbuffered output (Windows compatible)
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except:
        pass

def read_inputs_from_file(filename, file_ext):
    inside_inputs = False
    data = []
    
    if file_ext == 'chr':
        with open(filename, 'r', encoding='utf-16') as file:
            for line in file:
                # print(line)
                if '<inputs>' in line:
                    inside_inputs = True
                    continue
                elif '</inputs>' in line:
                    inside_inputs = False
                    continue
                if line.startswith('='):
                    blank = True
                else:
                    blank = False
                
                if inside_inputs and not blank:
                    data.append(line.strip())
                    
        if not data:
            raise ValueError(f"No inputs found in {filename}")
            
        df = pd.DataFrame([x.split('=') for x in data]).transpose()
        df.columns = df.iloc[0]
        df = df[1:]
        
    elif file_ext == 'set':
        # Try different encodings - UTF-16 first, then UTF-8, then latin-1
        file_encoding = None
        file_content = None
        
        for encoding in ['utf-16', 'utf-8', 'latin-1']:
            try:
                with open(filename, 'r', encoding=encoding) as file:
                    file_content = file.readlines()
                file_encoding = encoding
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
        
        if file_encoding is None or file_content is None:
            raise ValueError(f"Could not determine encoding for {filename}")
        
        # Process the content
        for line in file_content:
            if ';' not in line:
                first_part = line.split('||')[0].strip()
                data.append(first_part.split('='))
        
        if not data:
            raise ValueError(f"No data found in file {filename}")
        
        df = pd.DataFrame(data).transpose()
        if len(df) == 0:
            raise ValueError(f"Empty DataFrame created from {filename}")
        df.columns = df.iloc[0]
        df = df[1:]
    
    return df


    
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python sets2csv.py <directory_path>")
        sys.exit(1)

    # Directory containing your files
    directory = sys.argv[1]
    
    # Verify directory exists
    if not os.path.exists(directory):
        error_msg = f"Error: Directory does not exist: {directory}"
        print(error_msg, flush=True)
        log_path = os.path.join(directory, 'error_log.txt') if os.path.exists(os.path.dirname(directory)) else 'error_log.txt'
        try:
            with open(log_path, 'w') as f:
                f.write(error_msg + '\n')
        except:
            with open('error_log.txt', 'w') as f:
                f.write(error_msg + '\n')
        sys.exit(1)
    
    if not os.path.isdir(directory):
        error_msg = f"Error: Path is not a directory: {directory}"
        print(error_msg, flush=True)
        with open(os.path.join(directory, 'error_log.txt'), 'w') as f:
            f.write(error_msg + '\n')
        sys.exit(1)

    # Detect file types
    files = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
    has_set = any(f.lower().endswith('.set') for f in files)
    has_chr = any(f.lower().endswith('.chr') for f in files)

    if has_set and has_chr:
        error_msg = "Error: Input directory contains both *.set and *.chr files. Please provide a directory with only one type."
        print(error_msg, flush=True)
        with open(os.path.join(directory, 'error_log.txt'), 'w') as f:
            f.write(error_msg + '\n')
        sys.exit(1)
    
    if not has_set and not has_chr:
        error_msg = f"Error: No .set or .chr files found in {directory}"
        print(error_msg, flush=True)
        with open(os.path.join(directory, 'error_log.txt'), 'w') as f:
            f.write(error_msg + '\n')
        sys.exit(1)

    file_ext = 'set' if has_set else 'chr'
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = f'all_sets_{file_ext}_{timestamp}.csv'
    all_data = []

    for filename in files:
        if filename.lower().endswith('.' + file_ext):
            try:
                df = read_inputs_from_file(os.path.join(directory, filename), file_ext)
                # Add filename as first column
                df.insert(0, 'Filename', filename)
                all_data.append(df)
            except Exception as e:
                print(f"Error reading file {filename}: {e}")
                import traceback
                traceback.print_exc()
                continue
    
    # Concatenate all DataFrames
    if not all_data:
        error_msg = f"Error: No valid data could be extracted from any .{file_ext} files in {directory}"
        print(error_msg, flush=True)
        with open(os.path.join(directory, 'error_log.txt'), 'w') as f:
            f.write(error_msg + '\n')
        sys.exit(1)

    try:
        final_df = pd.concat(all_data, ignore_index=True)
        final_df.to_csv(os.path.join(directory, out_file), index=False)
        success_msg = f"Data has been written to {os.path.join(directory, out_file)}"
        print(success_msg, flush=True)
    except Exception as e:
        error_msg = f"Error processing files: {e}"
        print(error_msg, flush=True)
        import traceback
        traceback.print_exc()
        # Write error to log file in target directory
        with open(os.path.join(directory, 'error_log.txt'), 'w') as f:
            f.write(error_msg + '\n')
            traceback.print_exc(file=f)
        sys.exit(1)

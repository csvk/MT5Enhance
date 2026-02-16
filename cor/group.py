import csv
import random
import os
import datetime
import json
import argparse

def load_correlation_data(filepath):
    correlations = {}
    pairs = set()
    with open(filepath, 'r') as f:
        reader = csv.reader(f)
        header_found = False
        for row in reader:
            if not row or len(row) < 7:
                continue
            if row[0] == 'pair1' and row[1] == 'pair2':
                header_found = True
                continue
            if not header_found:
                continue
            
            p1, p2, daily_cor = row[0], row[1], row[6]
            try:
                val = float(daily_cor)
                correlations[(p1, p2)] = val
                pairs.add(p1)
                pairs.add(p2)
            except ValueError:
                continue
    return sorted(list(pairs)), correlations

def get_high_cor_count(bucket, correlations):
    count = 0
    for i in range(len(bucket)):
        for j in range(i + 1, len(bucket)):
            p1, p2 = bucket[i], bucket[j]
            val = correlations.get((p1, p2))
            if val is None:
                val = correlations.get((p2, p1), 100.0)
            if abs(val) >= 65:
                count += 1
    return count

def calculate_score(buckets, correlations):
    score = 0
    high_cor_count = 0
    bucket_high_cor_counts = []
    
    for bucket in buckets:
        curr_bucket_high_cor = 0
        for i in range(len(bucket)):
            for j in range(i + 1, len(bucket)):
                p1, p2 = bucket[i], bucket[j]
                val = correlations.get((p1, p2))
                if val is None:
                    val = correlations.get((p2, p1), 100.0)
                
                abs_val = abs(val)
                score += abs_val
                if abs_val >= 65:
                    high_cor_count += 1
                    curr_bucket_high_cor += 1
        bucket_high_cor_counts.append(curr_bucket_high_cor)
    
    # Penalize the total count of high correlations heavily
    # Penalize the "max" high correlation count in any single bucket even more heavily to distribute them
    max_high_cor = max(bucket_high_cor_counts) if bucket_high_cor_counts else 0
    return high_cor_count * 10000 + max_high_cor * 100000 + score

def group_pairs(pairs, correlations, num_buckets=5):
    best_buckets = None
    best_score = float('inf')
    
    # Try more random restarts for a deeper search
    for _ in range(100):
        current_buckets = [[] for _ in range(num_buckets)]
        pair_list = list(pairs)
        random.shuffle(pair_list)
        for i, p in enumerate(pair_list):
            current_buckets[i % num_buckets].append(p)
        
        current_score = calculate_score(current_buckets, correlations)
        
        improved = True
        while improved:
            improved = False
            # Randomly shuffle buckets to browse
            b_indices = list(range(num_buckets))
            random.shuffle(b_indices)
            
            for b_idx in b_indices:
                if not current_buckets[b_idx]: continue
                
                # Randomly shuffle pairs within bucket
                p_indices = list(range(len(current_buckets[b_idx])))
                random.shuffle(p_indices)
                
                for p_idx in p_indices:
                    p = current_buckets[b_idx][p_idx]
                    
                    target_b_indices = list(range(num_buckets))
                    random.shuffle(target_b_indices)
                    
                    for target_b_idx in target_b_indices:
                        if b_idx == target_b_idx: continue
                        
                        # Move
                        item = current_buckets[b_idx].pop(p_idx)
                        current_buckets[target_b_idx].append(item)
                        new_score = calculate_score(current_buckets, correlations)
                        
                        if new_score < current_score:
                            current_score = new_score
                            improved = True
                            break # Found improvement, restart bucket loops
                        else:
                            # Move back
                            current_buckets[target_b_idx].pop()
                            current_buckets[b_idx].insert(p_idx, item)
                    if improved: break
                if improved: break
        
        if current_score < best_score:
            best_score = current_score
            best_buckets = [list(b) for b in current_buckets]
            
    return best_buckets

def get_all_bucket_mergers(original_buckets, correlations):
    import itertools
    mergers = []
    num_orig = len(original_buckets)
    # Get all possible combinations of 2 original buckets
    for i, j in itertools.combinations(range(num_orig), 2):
        items = original_buckets[i] + original_buckets[j]
        h_cor = get_high_cor_count(items, correlations)
        mergers.append({
            'indices': (i + 1, j + 1),
            'items': items,
            'high_cor': h_cor
        })
    # Sort by high correlation count for clarity
    mergers.sort(key=lambda x: x['high_cor'])
    return mergers
    
def group_pairs_max_inclusion(pairs, correlations, num_buckets=3, max_high_cor=1):
    best_buckets = None
    max_pairs_included = -1
    best_score = float('inf')
    
    for _ in range(100):
        current_buckets = [[] for _ in range(num_buckets)]
        pair_list = list(pairs)
        random.shuffle(pair_list)
        
        # Try to fill buckets while maintaining constraint
        included_pairs = set()
        for p in pair_list:
            best_target = -1
            min_high_cor_increase = float('inf')
            
            for b_idx in range(num_buckets):
                current_buckets[b_idx].append(p)
                h_count = get_high_cor_count(current_buckets[b_idx], correlations)
                current_buckets[b_idx].pop()
                
                if h_count <= max_high_cor:
                    if h_count < min_high_cor_increase:
                        min_high_cor_increase = h_count
                        best_target = b_idx
            
            if best_target != -1:
                current_buckets[best_target].append(p)
                included_pairs.add(p)
        
        num_included = len(included_pairs)
        total_high_cor = sum(get_high_cor_count(b, correlations) for b in current_buckets)
        
        if num_included > max_pairs_included:
            max_pairs_included = num_included
            best_buckets = [list(b) for b in current_buckets]
            best_score = total_high_cor
        elif num_included == max_pairs_included:
            if total_high_cor < best_score:
                best_score = total_high_cor
                best_buckets = [list(b) for b in current_buckets]
                
    return best_buckets

def generate_md_report(buckets, mergers, three_buckets, pairs_count, correlations, output_path, seed=None, manual_used=False):
    with open(output_path, 'w') as f:
        f.write("# FX Pair Correlation Buckets\n\n")
        
        mode_str = "Manual Buckets (Provided by User)" if manual_used else "Optimization Search (Automated)"
        f.write(f"**Grouping Mode:** `{mode_str}`\n\n")
        
        if seed is not None:
            f.write(f"**Random Seed used:** `{seed}`\n\n")
        else:
            f.write("**Random Seed used:** `None (Non-deterministic)`\n\n")
            
        f.write("## Original 5 Buckets\n")
        f.write("Pairs grouped into 5 buckets to minimize intra-bucket absolute correlation (Daily).\n\n")
        
        for idx, bucket in enumerate(buckets):
            write_bucket_table(f, f"Bucket {idx + 1}", bucket, correlations)

        f.write("## Bucket Merger Analysis (All 10 Combinations)\n")
        f.write("Correlation analysis for all possible combinations of 2 original buckets.\n\n")
        
        # Summary table
        f.write("| Combination | High Correlations (abs >= 65) |\n")
        f.write("|-------------|-------------------------------|\n")
        for m in mergers:
            idx1, idx2 = m['indices']
            f.write(f"| Buckets {idx1} + {idx2} | {m['high_cor']} |\n")
        f.write("\n")

        for m in mergers:
            idx1, idx2 = m['indices']
            f.write(f"### Merged Buckets {idx1} + {idx2}\n\n")
            f.write(f"Total High Correlations: {m['high_cor']}\n\n")
            write_bucket_table(f, None, m['items'], correlations)

        f.write("## Max Inclusion 3-Bucket Configuration\n")
        f.write("Three buckets maximizing the number of pairs included with at most 1 high correlation per bucket.\n\n")
        included_count = sum(len(b) for b in three_buckets)
        f.write(f"Total pairs included: {included_count} / {pairs_count}\n\n")
        for idx, bucket in enumerate(three_buckets):
            write_bucket_table(f, f"Inclusion Bucket {idx + 1}", bucket, correlations)

def write_bucket_table(f, title, bucket, correlations):
    if title:
        f.write(f"### {title}\n\n")
    if not bucket:
        f.write("No pairs in this bucket.\n\n")
        return
    
    f.write("| | " + " | ".join(bucket) + " |\n")
    f.write("|---" + "|---" * len(bucket) + "|\n")
    for p1 in bucket:
        row = [p1]
        for p2 in bucket:
            if p1 == p2:
                row.append("100")
            else:
                val = correlations.get((p1, p2))
                if val is None:
                    val = correlations.get((p2, p1))
                
                if val is not None:
                    if abs(val) >= 65:
                        row.append(f'<span style="color:red">**{val}**</span>')
                    else:
                        row.append(str(val))
                else:
                    row.append("N/A")
        f.write("| " + " | ".join(row) + " |\n")
    f.write("\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FX Pair Correlation Grouping Tool")
    parser.add_argument("--csv", default=r'd:\Trading\MT5Enhance\cor\correlation.csv', help="Path to correlation CSV file")
    parser.add_argument("--manual", help="Path to JSON file containing manual buckets (e.g., cor/buckets.json)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility (default: 42)")
    args = parser.parse_args()

    # Set random seed
    if args.seed is not None:
        random.seed(args.seed)
        print(f"Using random seed: {args.seed}")
    else:
        print("Running in non-deterministic mode (no seed).")

    pairs, correlations = load_correlation_data(args.csv)
    
    final_buckets = None
    if args.manual:
        if os.path.exists(args.manual):
            print(f"Loading manual buckets from {args.manual}")
            with open(args.manual, 'r') as f:
                final_buckets = json.load(f)
        else:
            print(f"Error: Manual buckets file {args.manual} not found.")
            exit(1)
    else:
        print("Running optimization search for 5 buckets...")
        final_buckets = group_pairs(pairs, correlations)
    
    # 1. Prepare all 10 bucket mergers
    mergers = get_all_bucket_mergers(final_buckets, correlations)
    
    # 2. Max inclusion 3-bucket logic
    three_buckets = group_pairs_max_inclusion(pairs, correlations, num_buckets=3, max_high_cor=1)
    
    # Create filename with datetime suffix
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_filename = f"buckets_report_{timestamp}.md"
    report_path = os.path.join(os.path.dirname(args.csv), report_filename)
    
    generate_md_report(final_buckets, mergers, three_buckets, len(pairs), correlations, report_path, seed=args.seed, manual_used=(args.manual is not None))
    print(f"Report generated at {report_path}")

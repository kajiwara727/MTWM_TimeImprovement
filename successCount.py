import re
import pandas as pd
from collections import defaultdict
import glob
import sys
import os

def parse_summary_file(file_name):
    """
    サマリーファイルをパースして、ランごとのデータを抽出する関数。
    """
    run_data = {}
    current_run_name = None
    
    try:
        with open(file_name, 'r', encoding='utf-8') as f:
            for line in f:
                run_name_match = re.search(r"Run Name: (run_\d+)", line)
                if run_name_match:
                    current_run_name = run_name_match.group(1)
                    if current_run_name not in run_data:
                        run_data[current_run_name] = {}

                if current_run_name:
                    # --- MOD: Start ---
                    # 各項目（waste, reagents, ops）が辞書に存在しない（まだセットされていない）場合のみ、
                    # 正規表現にマッチしたら値をセットする（上書き防止）

                    # Waste
                    if 'waste' not in run_data[current_run_name]:
                        waste_match = re.search(r"Total Waste Generated: (\d+\.?\d*)", line)
                        if not waste_match:
                            waste_match = re.search(r"Minimum Waste Found: (\d+\.?\d*)", line)
                        if waste_match:
                            run_data[current_run_name]['waste'] = float(waste_match.group(1))

                    # Reagents
                    if 'reagents' not in run_data[current_run_name]:
                        reagent_match = re.search(r"Total Reagent Units: (\d+)", line)
                        if reagent_match:
                            run_data[current_run_name]['reagents'] = int(reagent_match.group(1))

                    # Ops
                    if 'ops' not in run_data[current_run_name]:
                        ops_match = re.search(r"(?:Total )?Operations: (\d+)", line)
                        if ops_match:
                             run_data[current_run_name]['ops'] = int(ops_match.group(1))
                    # --- MOD: End ---
                        
    except FileNotFoundError:
        print(f"エラー: ファイル '{file_name}' が見つかりません。")
        return None
    except Exception as e:
        print(f"エラー: ファイル '{file_name}' の処理中にエラーが発生しました: {e}")
        return None
        
    if not run_data:
        print(f"エラー: ファイル '{file_name}' からデータを抽出できませんでした。")
        return None
        
    incomplete_runs = []
    required_keys = ['waste', 'reagents', 'ops']
    for run, data in run_data.items():
        if not all(key in data for key in required_keys):
            incomplete_runs.append(run)
            
    if incomplete_runs:
        print(f"警告: データが不完全なため、以下のランを除外しました: {', '.join(incomplete_runs)}")
        for run in incomplete_runs:
            del run_data[run]

    return run_data

def print_ops_analysis(data_pairs, sort_reverse=True): # MOD: sort_reverse引数を追加
    """
    操作数分析を表示するヘルパー関数
    sort_reverse: True=降順 (削減量大), False=昇順 (増加量大)
    """
    if not data_pairs:
        print("   該当するケースはありません。")
        return

    # 廃棄削減量(引数で指定) -> 試薬削減量(引数で指定) でソート
    # 元のロジック (タプル全体でのソート) を維持
    sorted_pairs = sorted(data_pairs.items(), key=lambda x: (x[0][0], x[0][1]), reverse=sort_reverse)
    
    for (w_red, r_red), ops_red_list in sorted_pairs:
        # 廃棄の表示
        w_text = f"{w_red:.1f}減" if w_red > 0 else (f"{abs(w_red):.1f}増" if w_red < 0 else "維持(±0)")
        # 試薬の表示
        r_text = f"{r_red}減" if r_red > 0 else (f"{abs(r_red)}増" if r_red < 0 else "維持(±0)")
        
        print(f"\n[ケース] 廃棄: {w_text}, 試薬: {r_text} (合計 {len(ops_red_list)} 件)")
        
        ops_counts = defaultdict(int)
        for op_red in ops_red_list:
            ops_counts[op_red] += 1
        
        sorted_ops = sorted(ops_counts.items(), key=lambda x: x[0], reverse=True)
        for op_red, count in sorted_ops:
            if op_red > 0:
                print(f"   - 操作数 {op_red} 削減: {count} 件")
            elif op_red < 0:
                print(f"   - 操作数 {abs(op_red)} 増加: {count} 件")
            else:
                print(f"   - 操作数 維持 (±0): {count} 件")

# --- メインの処理 ---

# 1. ファイル名の設定
previous_file = "_comparison__summary.txt"

search_pattern = "*_random_summary.txt"
print(f"パターン '{search_pattern}' で提案手法(Proposed)のファイルを検索します...")
proposed_files_found = glob.glob(search_pattern)

proposed_file = ""

if len(proposed_files_found) == 0:
    print(f"エラー: パターン '{search_pattern}' に一致するファイルが見つかりません。")
    sys.exit()

elif len(proposed_files_found) == 1:
    proposed_file = proposed_files_found[0]
    print(f"ファイル '{proposed_file}' を自動的に検出しました。")

else:
    print(f"パターン '{search_pattern}' に一致するファイルが複数見つかりました:")
    for i, f in enumerate(proposed_files_found):
        print(f"   [{i+1}] {f}")
    
    selected_index = -1
    while selected_index < 0 or selected_index >= len(proposed_files_found):
        try:
            choice = input(f"使用するファイルの番号 (1-{len(proposed_files_found)}) を入力してください: ")
            selected_index = int(choice) - 1
            if selected_index < 0 or selected_index >= len(proposed_files_found):
                print("無効な番号です。")
        except ValueError:
            print("数値を入力してください。")
    
    proposed_file = proposed_files_found[selected_index]
    print(f"'{proposed_file}' を使用します。")


print(f"\n従来手法ファイル(Previous): {previous_file}")
print(f"提案手法ファイル(Proposed): {proposed_file}")

# 2. ファイルのパース
previous_data = parse_summary_file(previous_file)
proposed_data = parse_summary_file(proposed_file)

if not previous_data or not proposed_data:
    print("両方のファイルのパースに成功しなかったため、処理を中断します。")
else:
    common_runs = sorted(list(set(previous_data.keys()) & set(proposed_data.keys())))
    
    if not common_runs:
        print("比較対象の共通ランが見つかりませんでした。")
    else:
        print(f"\n合計 {len(common_runs)} 件の共通ランを比較します。")

        # 分析用データの格納庫
        ops_analysis_positive = defaultdict(list) # 廃棄削減 > 0
        ops_analysis_negative = defaultdict(list) # 廃棄削減 <= 0
        
        comparison_results = []

        for run_name in common_runs:
            prev_run = previous_data[run_name]
            prop_run = proposed_data[run_name]

            prev_waste = prev_run['waste']
            prop_waste = prop_run['waste']
            prev_reagents = prev_run['reagents']
            prop_reagents = prop_run['reagents']
            prev_ops = prev_run['ops']
            prop_ops = prop_run['ops']

            waste_reduction = prev_waste - prop_waste
            reagent_reduction = prev_reagents - prop_reagents
            ops_reduction = prev_ops - prop_ops
            
            # 勝者判定
            waste_winner = "DRAW"
            if prop_waste < prev_waste:
                waste_winner = "WIN"
            elif prev_waste < prop_waste:
                waste_winner = "LOSE"

            reagent_winner = "DRAW"
            if prop_reagents < prev_reagents:
                reagent_winner = "WIN"
            elif prev_reagents < prop_reagents:
                reagent_winner = "LOSE"

            # 分析用にデータを振り分け
            if waste_reduction > 0:
                ops_analysis_positive[(waste_reduction, reagent_reduction)].append(ops_reduction)
            else:
                ops_analysis_negative[(waste_reduction, reagent_reduction)].append(ops_reduction)

            comparison_results.append({
                'Run Name': run_name,
                'Waste Result': waste_winner,
                'Waste Reduction': waste_reduction,
                'Proposed Waste': prop_waste,
                'Previous Waste': prev_waste,
                'Reagent Result': reagent_winner,
                'Reagent Reduction': reagent_reduction,
                'Proposed Reagents': prop_reagents,
                'Previous Reagents': prev_reagents,
                'Ops Reduction': ops_reduction, # CSV出力用にOps Reductionも追加
                'Proposed Ops': prop_ops,
                'Previous Ops': prev_ops
            })

        # --- 分析結果の表示 ---
        print("\n--- 廃棄削減 ( > 0 ) のケース [削減量が多い順] ---")
        print_ops_analysis(ops_analysis_positive, sort_reverse=True) # MOD: 降順 (削減量大)

        print("\n--- 廃棄維持・増加 ( <= 0 ) のケース [増加量が多い順] ---")
        print_ops_analysis(ops_analysis_negative, sort_reverse=False) # MOD: 昇順 (増加量大)

        # CSVファイル出力
        try:
            output_dir = "CSV_Result"
            os.makedirs(output_dir, exist_ok=True)

            base_name = os.path.splitext(os.path.basename(proposed_file))[0]
            output_csv_path = os.path.join(output_dir, f"{base_name}_comparison.csv") # MOD: ファイル名変更
            
            df_results = pd.DataFrame(comparison_results)

            df_results.sort_values(by=['Waste Reduction', 'Reagent Reduction'], 
                                   ascending=[False, False], 
                                   inplace=True)

            column_order = [
                'Run Name', 
                'Waste Result', 'Waste Reduction', 'Proposed Waste', 'Previous Waste',
                'Reagent Result', 'Reagent Reduction', 'Proposed Reagents', 'Previous Reagents',
                'Ops Reduction', 'Proposed Ops', 'Previous Ops' # MOD: Opsカラム追加
            ]
            existing_cols = [col for col in column_order if col in df_results.columns]
            df_results = df_results[existing_cols]

            df_results.to_csv(output_csv_path, index=False, encoding='utf-8-sig')
            print(f"\n詳細な比較結果を '{output_csv_path}' に保存しました。")
        except Exception as e:
            print(f"エラー: CSVファイルへの保存中にエラーが発生しました: {e}")
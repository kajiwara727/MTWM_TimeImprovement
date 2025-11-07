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
                    waste_match = re.search(r"Total Waste Generated: (\d+\.?\d*)", line)
                    if not waste_match:
                        waste_match = re.search(r"Minimum Waste Found: (\d+\.?\d*)", line)
                    
                    if waste_match:
                        run_data[current_run_name]['waste'] = float(waste_match.group(1))

                    reagent_match = re.search(r"Total Reagent Units: (\d+)", line)
                    if reagent_match:
                        run_data[current_run_name]['reagents'] = int(reagent_match.group(1))
                        
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
    for run, data in run_data.items():
        if 'waste' not in data or 'reagents' not in data:
            incomplete_runs.append(run)
            
    if incomplete_runs:
        for run in incomplete_runs:
            del run_data[run]

    return run_data

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
        print(f"  [{i+1}] {f}")
    
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
print(f"提案手法ファイル(Proposed): {proposed_file}\n")

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
        print(f"合計 {len(common_runs)} 件の共通ランを比較します。")

        waste_reduced_count = 0
        waste_and_reagent_reduced_count = 0
        waste_reduction_amounts = defaultdict(int)
        reduction_pairs = defaultdict(int)
        comparison_results = []

        for run_name in common_runs:
            if run_name not in previous_data or run_name not in proposed_data:
                continue
            prev_run = previous_data[run_name]
            prop_run = proposed_data[run_name]
            
            if 'waste' not in prev_run or 'reagents' not in prev_run or \
               'waste' not in prop_run or 'reagents' not in prop_run:
                continue

            prev_waste = prev_run['waste']
            prop_waste = prop_run['waste']
            prev_reagents = prev_run['reagents']
            prop_reagents = prop_run['reagents']

            # 削減量の計算
            waste_reduction = prev_waste - prop_waste
            reagent_reduction = prev_reagents - prop_reagents
            
            # 勝者判定
            waste_winner = "DRAW"
            if prop_waste < prev_waste:
                waste_winner = "WIN"
                waste_reduced_count += 1
                waste_reduction_amounts[waste_reduction] += 1
                if prop_reagents < prev_reagents:
                    waste_and_reagent_reduced_count += 1
            elif prev_waste < prop_waste:
                waste_winner = "LOSE"

            reagent_winner = "DRAW"
            if prop_reagents < prev_reagents:
                reagent_winner = "WIN"
            elif prev_reagents < prop_reagents:
                reagent_winner = "LOSE"

            if waste_reduction >= 0 and reagent_reduction >= 0:
                if waste_reduction > 0 or reagent_reduction > 0:
                    reduction_pairs[(waste_reduction, reagent_reduction)] += 1

            comparison_results.append({
                'Run Name': run_name,
                'Waste Result': waste_winner,
                'Waste Reduction': waste_reduction,
                'Proposed Waste': prop_waste,
                'Previous Waste': prev_waste,
                'Reagent Result': reagent_winner,
                'Reagent Reduction': reagent_reduction,
                'Proposed Reagents': prop_reagents,
                'Previous Reagents': prev_reagents
            })

        # 結果サマリー出力
        print("\n--- 比較結果サマリー (提案手法 vs 従来手法) ---")
        print(f"\n[要求1] 廃棄量が減ったケース (WIN):")
        print(f"  {len(common_runs)} 件中 {waste_reduced_count} 件")

        print(f"\n[要求2] 廃棄量の削減量ごとのケース数:")
        if not waste_reduction_amounts:
            print("  なし")
        else:
            sorted_reductions = sorted(waste_reduction_amounts.items(), reverse=True)
            for amount, count in sorted_reductions:
                print(f"  削減量 {amount:.1f}: {count} 件")

        print(f"\n[要求3] 廃棄量と試薬数の両方を減らせたケース (Double WIN):")
        print(f"  {waste_reduced_count} 件中 {waste_and_reagent_reduced_count} 件")

        print(f"\n[要求4] 廃棄液滴と試薬数の削減量ペアごとのケース数 (両方維持以上):")
        if not reduction_pairs:
            print("  なし")
        else:
            sorted_pairs = sorted(reduction_pairs.items(), key=lambda x: (x[0][0], x[0][1]), reverse=True)
            for (w_red, r_red), count in sorted_pairs:
                print(f"  廃棄 {w_red:.1f}減, 試薬 {r_red}減 : {count} 件")
        
        # CSVファイル出力
        try:
            output_dir = "CSV_Result"
            os.makedirs(output_dir, exist_ok=True)

            base_name = os.path.splitext(os.path.basename(proposed_file))[0]
            output_csv_path = os.path.join(output_dir, f"comparison_result_{base_name}.csv")
            
            df_results = pd.DataFrame(comparison_results)

            df_results.sort_values(by=['Waste Reduction', 'Reagent Reduction'], 
                                   ascending=[False, False], 
                                   inplace=True)

            column_order = [
                'Run Name', 
                'Waste Result', 'Waste Reduction', 'Proposed Waste', 'Previous Waste',
                'Reagent Result', 'Reagent Reduction', 'Proposed Reagents', 'Previous Reagents'
            ]
            existing_cols = [col for col in column_order if col in df_results.columns]
            df_results = df_results[existing_cols]

            df_results.to_csv(output_csv_path, index=False, encoding='utf-8-sig')
            print(f"\n--- 詳細データ ---")
            print(f"詳細な比較結果を '{output_csv_path}' に保存しました。")
            print("(WINが上に来るようにソートされています)")
        except Exception as e:
            print(f"エラー: CSVファイルへの保存中にエラーが発生しました: {e}")
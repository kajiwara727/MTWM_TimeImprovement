import re
import pandas as pd
from collections import defaultdict
import glob  # <--- ファイル検索のために追加
import sys   # <--- エラー終了のために追加

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
        print(f"警告: '{file_name}' の以下のランでデータが不足しています: {incomplete_runs}")
        for run in incomplete_runs:
            del run_data[run]

    return run_data

# --- メインの処理 ---

# 1. ファイル名の設定
# 比較対象のファイル (固定)
comparison_file = "_comparison__summary.txt"

# ★★★ ランダム手法のファイルを自動検索 ★★★
search_pattern = "*_random_summary.txt"
print(f"パターン '{search_pattern}' でランダム手法のファイルを検索します...")
random_files_found = glob.glob(search_pattern)

random_file = "" # 使用するファイル名を格納する変数

if len(random_files_found) == 0:
    print(f"エラー: パターン '{search_pattern}' に一致するファイルが見つかりません。")
    print("スクリプトと同じディレクトリにファイルが存在するか確認してください。")
    sys.exit() # プログラムを終了

elif len(random_files_found) == 1:
    # ファイルが1つだけ見つかった場合、自動でそれを使用
    random_file = random_files_found[0]
    print(f"ファイル '{random_file}' を自動的に検出しました。")

else:
    # ファイルが複数見つかった場合、ユーザーに選択させる
    print(f"パターン '{search_pattern}' に一致するファイルが複数見つかりました:")
    for i, f in enumerate(random_files_found):
        print(f"  [{i+1}] {f}")
    
    selected_index = -1
    while selected_index < 0 or selected_index >= len(random_files_found):
        try:
            choice = input(f"使用するファイルの番号 (1-{len(random_files_found)}) を入力してください: ")
            selected_index = int(choice) - 1
            if selected_index < 0 or selected_index >= len(random_files_found):
                print("無効な番号です。")
        except ValueError:
            print("数値を入力してください。")
    
    random_file = random_files_found[selected_index]
    print(f"'{random_file}' を使用します。")

# ★★★ ここまでが修正箇所 ★★★


print(f"\n比較手法ファイル: {comparison_file}")
print(f"ランダム手法ファイル: {random_file}\n")

# 2. ファイルのパース
comparison_data = parse_summary_file(comparison_file)
random_data = parse_summary_file(random_file)

if not comparison_data or not random_data:
    print("両方のファイルのパースに成功しなかったため、処理を中断します。")
else:
    common_runs = sorted(list(set(comparison_data.keys()) & set(random_data.keys())))
    
    if not common_runs:
        print("比較対象の共通ランが見つかりませんでした。")
    else:
        print(f"合計 {len(common_runs)} 件の共通ランを比較します。")

        # 3. 集計の初期化
        waste_reduced_count = 0
        waste_and_reagent_reduced_count = 0
        reduction_amounts = defaultdict(int)
        comparison_results = []

        # 4. データの比較と集計
        for run_name in common_runs:
            if run_name not in comparison_data or run_name not in random_data:
                continue
            comp_run = comparison_data[run_name]
            rand_run = random_data[run_name]
            
            if 'waste' not in comp_run or 'reagents' not in comp_run or \
               'waste' not in rand_run or 'reagents' not in rand_run:
                print(f"警告: {run_name} のデータが不完全なため、スキップします。")
                continue

            comp_waste = comp_run['waste']
            rand_waste = rand_run['waste']
            comp_reagents = comp_run['reagents']
            rand_reagents = rand_run['reagents']

            waste_reduction = comp_waste - rand_waste
            
            # 要求1: 廃棄量が減ったケース (ランダム < 比較)
            if rand_waste < comp_waste:
                waste_reduced_count += 1
                reduction_amounts[waste_reduction] += 1
                
                # 要求3: 廃棄量も試薬数も減ったケース (ランダム < 比較)
                if rand_reagents < comp_reagents:
                    waste_and_reagent_reduced_count += 1

            comparison_results.append({
                'Run Name': run_name,
                'Comparison Waste': comp_waste,
                'Random Waste': rand_waste,
                'Waste Reduction (Comp - Rand)': waste_reduction,
                'Comparison Reagents': comp_reagents,
                'Random Reagents': rand_reagents,
                'Reagent Reduction (Comp - Rand)': comp_reagents - rand_reagents
            })

        # 5. 結果の出力
        print("\n--- 比較結果サマリー (ランダム vs 比較) ---")
        
        print(f"\n[要求1] 廃棄量が減ったケース:")
        print(f"ランダム手法が比較手法より廃棄量を減らせたケースは、{len(common_runs)} 件中 {waste_reduced_count} 件でした。")

        print(f"\n[要求2] 廃棄量の削減量ごとのケース数（廃棄量が減った {waste_reduced_count} 件の内訳）:")
        if not reduction_amounts:
            print("  廃棄量が減ったケースはありませんでした。")
        else:
            sorted_reductions = sorted(reduction_amounts.items())
            for amount, count in sorted_reductions:
                print(f"  廃棄量を {amount} 減らせたケース: {count} 件")

        print(f"\n[要求3] 廃棄量と試薬数の両方を減らせたケース:")
        print(f"廃棄量を減らせた {waste_reduced_count} 件のうち、同時に試薬数も減らすことができたケースは {waste_and_reagent_reduced_count} 件でした。")
        
        # 6. 詳細な比較結果をCSVファイルに出力
        try:
            output_csv_path = "random_vs_comparison_summary.csv"
            df_results = pd.DataFrame(comparison_results)
            df_results.to_csv(output_csv_path, index=False, encoding='utf-8-sig')
            print(f"\n--- 詳細データ ---")
            print(f"全ランの詳細な比較結果を '{output_csv_path}' に保存しました。")
        except Exception as e:
            print(f"エラー: CSVファイルへの保存中にエラーが発生しました: {e}")
import os


def _calculate_and_save_summary(
    run_results, output_dir, summary_filename, title_prefix, objective_mode
):
    """
    複数の実行結果(run_results)を受け取り、
    それらの平均値などを計算し、サマリーファイルとして保存する共通内部関数。
    
    'random' と 'file_load' (comparison) モードで使用されます。

    Args:
        run_results (list): 実行結果のリスト
        output_dir (str): 保存先の親ディレクトリ
        summary_filename (str): 保存するサマリーファイル名 (例: "MyRun_summary.txt")
        title_prefix (str): レポートのタイトル (例: "Random")
        objective_mode (str): 最適化モード
    """
    # ファイル名を summary_filename 引数から直接決定する
    filepath = os.path.join(output_dir, summary_filename)

    content = [
        "==================================================",
        f"      Summary of All {title_prefix} Simulation Runs       ",
        "==================================================",
        f"\nTotal simulations executed: {len(run_results)}\n",
    ]

    # --- 1. 各実行の詳細をリストアップ ---
    for run_result in run_results:
        content.append("-" * 50)
        content.append(f"Run Name: {run_result['run_name']}")
        content.append(f"  -> Execution Time: {run_result['elapsed_time']:.2f} seconds")

        if run_result["final_value"] is not None:
            # 解が見つかった場合
            mode_lower = objective_mode.lower()
            objective_label = "Final Objective Value"
            if mode_lower == "waste":
                objective_label = "Minimum Waste Found"
            elif mode_lower == "operations":
                objective_label = "Minimum Operations Found"
            elif mode_lower == "reagents":
                objective_label = "Minimum Reagents Found"

            content.append(f"  -> {objective_label}: {run_result['final_value']}")
            content.append(
                f"  -> Total Operations: {run_result.get('total_operations', 'N/A')}"
            )
            content.append(
                f"  -> Total Reagent Units: {run_result.get('total_reagents', 'N/A')}"
            )
            content.append(
                f"  -> Total Waste Generated: {run_result.get('total_waste', 'N/A')}"
            )
        else:
            # 解が見つからなかった場合
            content.append("  -> No solution was found for this configuration.")

        # 実行に使われた設定 (ratios) も記載
        if "config" in run_result and run_result["config"]:
            content.append("  -> Target Configurations:")
            for target_idx, config in enumerate(run_result["config"]):
                ratios_str = ", ".join(map(str, config["ratios"]))
                content.append(f"    - Target {target_idx+1}: Ratios = [{ratios_str}]")
            content.append("")

    # --- 2. 全実行の平均値を計算 ---
    
    # 解が見つかった実行のみをフィルタリング
    successful_runs = [res for res in run_results if res["final_value"] is not None]
    num_successful_runs = len(successful_runs)
    mode_label = objective_mode.title()

    if num_successful_runs > 0:
        # 安全に合計値を計算するヘルパー関数
        def sum_metric_safe(metric_key):
            return sum(
                run.get(metric_key, 0)
                for run in successful_runs
                if run.get(metric_key) is not None
                and isinstance(run.get(metric_key), (int, float))
            )

        # 各指標の合計値を計算
        total_objective_value = sum_metric_safe("final_value")
        total_waste = sum_metric_safe("total_waste")
        total_operations = sum_metric_safe("total_operations")
        total_reagents = sum_metric_safe("total_reagents")

        # 平均値を計算
        avg_objective_value = total_objective_value / num_successful_runs
        avg_waste = total_waste / num_successful_runs
        avg_operations = total_operations / num_successful_runs
        avg_reagents = total_reagents / num_successful_runs
        # --- ★★★ ---

        # 平均値のセクションをコンテンツに追加
        content.append("\n" + "=" * 50)
        content.append(
            f"        Average Results (based on {num_successful_runs} successful runs)        "
        )
        content.append("=" * 50)
        content.append(
            f"Average Objective Value ({mode_label}): {avg_objective_value:.2f}"
        )
        content.append(f"Average Total Waste: {avg_waste:.2f}")
        content.append(f"Average Total Operations: {avg_operations:.2f}")
        content.append(f"Average Total Reagent Units: {avg_reagents:.2f}")
        content.append("=" * 50)
    else:
        content.append("\nNo successful runs found to calculate averages.")

    # --- 3. ファイルへの保存 ---
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(content))
        print("\n" + "=" * 60)
        print(f"SUCCESS: A summary of all {title_prefix} runs has been saved to:")
        print(f"  -> {filepath}")
        print("=" * 60)
        return True
    except IOError as e:
        print(f"\nError saving {title_prefix} run summary file: {e}")
        return False

# --- 公開関数 (各Runnerから呼び出される) ---

def save_random_run_summary(run_results, output_dir):
    """'random' モード用のサマリーを保存する"""
    objective_mode = "waste"
    if run_results and "objective_mode" in run_results[0]:
        objective_mode = run_results[0]["objective_mode"]

    # 親ディレクトリ名を取得 (例: "MyRun_random_a1b2c3d4")
    dir_name = os.path.basename(output_dir)
    # ファイル名を生成 (例: "MyRun_random_a1b2c3d4_summary.txt")
    summary_filename = f"{dir_name}_summary.txt"

    _calculate_and_save_summary(
        run_results, 
        output_dir, 
        summary_filename, # 変更: ファイル名を直接渡す
        "Random", 
        objective_mode
    )


def save_comparison_summary(run_results, output_dir, objective_mode):
    """'file_load' モード用のサマリーを保存する"""
    
    # 親ディレクトリ名を取得
    dir_name = os.path.basename(output_dir)
    # ファイル名を生成
    summary_filename = f"{dir_name}_summary.txt"

    _calculate_and_save_summary(
        run_results, 
        output_dir, 
        summary_filename, # 変更: ファイル名を直接渡す
        "Comparison", 
        objective_mode
    )


def save_permutation_summary(run_results, output_dir, objective_mode):
    """'auto_permutations' モード用のサマリーを保存する
       (平均値ではなく、ベスト/セカンドベストのパターンを報告する)
    """
    # 1. 成功した実行のみをフィルタリング
    successful_runs = [res for res in run_results if res["final_value"] is not None]

    if not successful_runs:
        print("\n[Permutation Summary] No successful runs found.")
        return

    # 2. 目的値 (例: 廃棄物量) でソート (昇順)
    successful_runs.sort(key=lambda x: x["final_value"])
    min_objective_value = successful_runs[0]["final_value"]

    # 3. ベストパターン (目的値が最小値と一致するもの全て) を抽出
    best_runs = [
        run for run in successful_runs if run["final_value"] == min_objective_value
    ]

    # 4. セカンドベストパターン (最小値より大きいもののうち最小の値) を抽出
    second_min_objective_value = None
    for run in successful_runs:
        if run["final_value"] > min_objective_value:
            second_min_objective_value = run["final_value"]
            break

    second_best_runs = []
    if second_min_objective_value is not None:
        second_best_runs = [
            run
            for run in successful_runs
            if run["final_value"] == second_min_objective_value
        ]

    # 5. レポートコンテンツの構築
    
    # 親ディレクトリ名を取得
    dir_name = os.path.basename(output_dir)
    # ファイル名を生成 (例: "MyPermutations_a1b2c3d4_summary.txt")
    filepath = os.path.join(output_dir, f"{dir_name}_summary.txt")
    
    objective_label = objective_mode.title()

    content = [
        "==========================================================================",
        f"        Permutation Analysis Summary (Objective: {objective_label})        ",
        "==========================================================================",
        f"\nTotal permutations run: {len(run_results)}",
        f"Successful runs: {len(successful_runs)}",
        f"Metric minimized: {objective_mode.upper()}",
        f"Note: If Optimization Mode is 'waste', this value represents the waste minimization.",
    ]

    # --- ベストパターン ---
    content.append("\n" + "=" * 80)
    content.append(f"🥇 BEST PATTERN(S): {objective_label} = {min_objective_value}")
    content.append("=" * 80)

    for i, best_run in enumerate(best_runs):
        content.append(f"\n--- Rank 1 Pattern {i+1} (Run: {best_run['run_name']}) ---")
        content.append(
            f"  Final Objective Value ({objective_label}): {best_run['final_value']}"
        )
        content.append(f"  Total Operations: {best_run.get('total_operations', 'N/A')}")
        content.append(
            f"  Total Reagent Units: {best_run.get('total_reagents', 'N/A')}"
        )
        content.append(f"  Total Waste: {best_run.get('total_waste', 'N/A')}")
        content.append(f"  Elapsed Time: {best_run['elapsed_time']:.2f} sec")
        content.append("  Target Permutation Structure:")
        # このパターンの 'factors' を表示
        for target_config in best_run["targets"]:
            ratios_str = ", ".join(map(str, target_config["ratios"]))
            factors_str = ", ".join(map(str, target_config["factors"]))
            content.append(
                f"    - {target_config['name']}: Ratios=[{ratios_str}], Factors=[{factors_str}]"
            )

    # --- セカンドベストパターン ---
    if second_min_objective_value is not None:
        content.append("\n" + "=" * 80)
        content.append(
            f"🥈 SECOND BEST PATTERN(S): {objective_label} = {second_min_objective_value}"
        )
        content.append("=" * 80)

        for i, second_best_run in enumerate(second_best_runs):
            content.append(
                f"\n--- Rank 2 Pattern {i+1} (Run: {second_best_run['run_name']}) ---"
            )
            # ... (ベストパターンと同様の詳細) ...
            content.append(
                f"  Final Objective Value ({objective_label}): {second_best_run['final_value']}"
            )
            content.append(
                f"  Total Operations: {second_best_run.get('total_operations', 'N/A')}"
            )
            content.append(
                f"  Total Reagent Units: {second_best_run.get('total_reagents', 'N/A')}"
            )
            content.append(
                f"  Total Waste: {second_best_run.get('total_waste', 'N/A')}"
            )
            content.append(f"  Elapsed Time: {second_best_run['elapsed_time']:.2f} sec")
            content.append("  Target Permutation Structure:")
            for target_config in second_best_run["targets"]:
                ratios_str = ", ".join(map(str, target_config["ratios"]))
                factors_str = ", ".join(map(str, target_config["factors"]))
                content.append(
                    f"    - {target_config['name']}: Ratios=[{ratios_str}], Factors=[{factors_str}]"
                )
    else:
        content.append("\nNo second best permutation found.")

    # 6. ファイル保存
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(content))
        print(f"\nPermutation summary saved to: {filepath}")
    except IOError as e:
        print(f"\nError saving permutation summary file: {e}")
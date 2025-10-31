import os
import random
import json
from .base_runner import BaseRunner  # 親クラス
from core import find_factors_for_sum
from utils import generate_random_ratios
from reporting import save_random_run_summary


class RandomRunner(BaseRunner):
    """
    'random' モードの実行を担当するクラス。
    config.py の RANDOM_... 変数に基づき、ランダムなシナリオを複数回実行します。
    """

    def run(self):
        """'random' モードのメイン実行ロジック"""
        
        # 1. Configからランダム実行用の設定を読み込む
        num_runs = self.config.RANDOM_K_RUNS          # 実行回数 (例: 100)
        num_targets = self.config.RANDOM_N_TARGETS   # 1回あたりのターゲット数 (例: 3)
        num_reagents = self.config.RANDOM_T_REAGENTS # 試薬の種類の数 (例: 3)
        
        # 比率の合計値 (S_ratio_sum) を決めるルール
        sequence = self.config.RANDOM_S_RATIO_SUM_SEQUENCE     # オプション1: 固定シーケンス
        candidates = self.config.RANDOM_S_RATIO_SUM_CANDIDATES # オプション2: 候補からランダム
        default_sum = self.config.RANDOM_S_RATIO_SUM_DEFAULT   # オプション3: デフォルト値
        
        run_name_prefix = self.config.RUN_NAME # config.pyのRUN_NAME (例: "ExperimentA")

        print(f"Preparing to run {num_runs} random simulations...")

        # 2. ベースとなる出力ディレクトリ名を決定
        
        # --- フォルダ名用の比率合計モード文字列を生成 ---
        # どの S_ratio_sum 設定が使われたかに基づいて文字列を決定
        ratio_sum_mode_str = ""
        if sequence and isinstance(sequence, list) and len(sequence) > 0:
            # オプション1 (固定シーケンス) が使われた場合
            # (要望に基づき multiplier は無視し、base_sum か数値のみを抽出)
            seq_parts = []
            for spec in sequence:
                if isinstance(spec, dict):
                    # 辞書の場合は 'base_sum' の値を取得
                    seq_parts.append(str(spec.get("base_sum", "Err")))
                elif isinstance(spec, (int, float)):
                    # 数値の場合はそのまま使用
                    seq_parts.append(str(spec))
            # 例: "Seq[18_18_24]"
            ratio_sum_mode_str = f"Seq[{'_'.join(seq_parts)}]"
            
        elif candidates and isinstance(candidates, list) and len(candidates) > 0:
            # オプション2 (候補リストからランダム) が使われた場合
            # 重複を除きソートして分かりやすくする (例: "Cand[18_24_30]")
            cand_parts = sorted(list(set(candidates))) 
            ratio_sum_mode_str = f"Cand[{'_'.join(map(str, cand_parts))}]"
            
        else:
            # オプション3 (デフォルト値) が使われた場合 (例: "Def[12]")
            ratio_sum_mode_str = f"Def[{default_sum}]"
        # --- ここまで ---

        # (RUN_NAME)-(濃度比)-(目標濃度数)-(試薬数)-(実行数) の順序に変更
        # (例: "ExperimentA-Def[12]-5targets-3reagents-100runs")
        base_run_name = f"{run_name_prefix}-{ratio_sum_mode_str}-{num_targets}targets-{num_reagents}reagents-{num_runs}runs"
        
        # ランダム実行は設定ハッシュが毎回変わるため、"random" という固定文字列でハッシュを生成
        base_output_dir = self._get_unique_output_directory_name(
            "random", base_run_name
        )
        os.makedirs(base_output_dir, exist_ok=True)
        print(f"All random run results will be saved under: '{base_output_dir}/'")

        all_run_results = []  # 全実行結果を保存するリスト (サマリー用)
        saved_configs = []    # 生成した全設定を保存するリスト (JSON出力用)

        # 3. 指定された回数 (num_runs) だけループを実行
        for run_idx in range(num_runs):
            print(
                f"\n{'='*20} Running Random Simulation {run_idx+1}/{num_runs} {'='*20}"
            )

            # 4. この回の実行で使用する「比率の合計値(S_ratio_sum)」を決定
            #    (config.py の設定に基づき、いずれか1つのオプションが選択される)
            specs_for_run = []
            if sequence and isinstance(sequence, list) and len(sequence) == num_targets:
                # オプション1: 固定シーケンス (configで定義されたリストをそのまま使用)
                specs_for_run = sequence
                print(
                    f"-> Mode: Fixed Sequence. Using S_ratio_sum specifications: {specs_for_run}"
                )
            elif candidates and isinstance(candidates, list) and len(candidates) > 0:
                # オプション2: 候補リストからランダム選択
                specs_for_run = [random.choice(candidates) for _ in range(num_targets)]
                print(
                    f"-> Mode: Random per Target. Generated S_ratio_sum specifications for this run: {specs_for_run}"
                )
            else:
                # オプション3: デフォルト値
                specs_for_run = [default_sum] * num_targets
                print(
                    f"-> Mode: Default. Using single S_ratio_sum '{default_sum}' for all targets."
                )

            # 5. この回の実行用の targets_config (ratios と factors) を動的に生成
            current_run_config = []
            valid_run = True  # このランダム設定が実行可能かどうかのフラグ
            
            # ターゲットの数 (num_targets) だけループ
            for target_idx in range(num_targets):
                spec = specs_for_run[target_idx]  # (例: 18 や {'base_sum': 18, 'multiplier': 5})
                
                # --- 'spec' を解析 ---
                base_sum = 0
                multiplier = 1
                if isinstance(spec, dict):
                    # 辞書形式の場合 (例: {'base_sum': 18, 'multiplier': 5})
                    # base_sum=18, multiplier=5
                    base_sum = spec.get("base_sum", 0)
                    multiplier = spec.get("multiplier", 1)
                elif isinstance(spec, (int, float)):
                    # 単純な数値の場合 (例: 18)
                    # base_sum=18, multiplier=1
                    base_sum = int(spec)
                    multiplier = 1
                else:
                    print(
                        f"Warning: Invalid spec format for target {target_idx+1}: {spec}. Skipping this run."
                    )
                    valid_run = False
                    break  # このシミュレーション (run_idx) を中止
                
                if base_sum <= 0:
                    print(
                        f"Warning: Invalid base_sum ({base_sum}) for target {target_idx+1}. Skipping this run."
                    )
                    valid_run = False
                    break

                # --- 'ratios' を生成 ---
                try:
                    # (例: num_reagents=3, base_sum=18)
                    # -> base_ratios = [2, 5, 11] (合計18)
                    base_ratios = generate_random_ratios(num_reagents, base_sum)
                    
                    # (例: base_ratios=[2, 5, 11], multiplier=5)
                    # -> ratios=[10, 25, 55] (合計 90)
                    ratios = [r * multiplier for r in base_ratios]
                    
                    print(f"  -> Target {target_idx+1}: Spec={spec}")
                    print(
                        f"     Base ratios (sum={base_sum}): {base_ratios} -> Multiplied by {multiplier} -> Final Ratios (sum={sum(ratios)}): {ratios}"
                    )
                except ValueError as e:
                    # (例: base_sum=2, num_reagents=3 の場合など)
                    print(
                        f"Warning: Could not generate base ratios for sum {base_sum}. Error: {e}. Skipping this run."
                    )
                    valid_run = False
                    break

                # --- 'factors' を生成 ---
                # (例: base_sum=18, MAX_MIXER_SIZE=5) -> [3, 3, 2]
                base_factors = find_factors_for_sum(
                    base_sum, self.config.MAX_MIXER_SIZE
                )
                if base_factors is None:
                    print(
                        f"Warning: Could not determine factors for base_sum {base_sum}. Skipping this run."
                    )
                    valid_run = False
                    break
                
                # (例: multiplier=5, MAX_MIXER_SIZE=5) -> [5]
                multiplier_factors = find_factors_for_sum(
                    multiplier, self.config.MAX_MIXER_SIZE
                )
                if multiplier_factors is None:
                    print(
                        f"Warning: Could not determine factors for multiplier {multiplier}. Skipping this run."
                    )
                    valid_run = False
                    break
                
                # 最終的な factors は、base と multiplier の factors を結合したもの
                # (例: [3, 3, 2] + [5] -> [3, 3, 2, 5])
                factors = base_factors + multiplier_factors
                factors.sort(reverse=True) # -> [5, 3, 3, 2] (降順ソート)
                print(
                    f"     Factors for base ({base_sum}): {base_factors} + Factors for multiplier ({multiplier}): {multiplier_factors} -> Sorted Final Factors: {factors}"
                )

                # 6. 生成した設定をリストに追加
                current_run_config.append(
                    {
                        "name": f"RandomTarget_{run_idx+1}_{target_idx+1}",
                        "ratios": ratios,
                        "factors": factors,
                    }
                )

            # 7. 生成した設定が不正(valid_run=False)だった場合、この回をスキップ
            if not valid_run or not current_run_config:
                continue

            # 8. 実行名と出力ディレクトリを決定 (ベースディレクトリの下に作成)
            run_name = f"run_{run_idx+1}"
            output_dir = os.path.join(base_output_dir, run_name)

            # 9. 単一最適化を実行 (親クラスの共通メソッド)
            (
                final_value,
                exec_time,
                total_ops,
                total_reagents,
                total_waste,
            ) = self._run_single_optimization(current_run_config, output_dir, run_name)

            # 10. 結果をサマリー用リストに保存
            all_run_results.append(
                {
                    "run_name": run_name,
                    "config": current_run_config, # ratios/factors も保存
                    "final_value": final_value,
                    "elapsed_time": exec_time,
                    "total_operations": total_ops,
                    "total_reagents": total_reagents,
                    "total_waste": total_waste,
                    "objective_mode": self.config.OPTIMIZATION_MODE,
                }
            )

            # 11. 設定を JSON 保存用リストにも保存
            saved_configs.append({"run_name": run_name, "targets": current_run_config})

        # --- 全実行 (num_runs) が完了 ---

        # 12. 全実行結果 (all_run_results) を渡し、サマリーファイル (平均値など) を生成
        save_random_run_summary(all_run_results, base_output_dir)
        
        # 13. 実行に使用した全設定 (saved_configs) を JSON ファイルとして保存
        #     (これにより 'file_load' モードでの再現が可能になる)
        config_log_path = os.path.join(base_output_dir, "random_configs.json")
        with open(config_log_path, "w", encoding="utf-8") as f:
            json.dump(saved_configs, f, indent=4)
        print(f"\nAll generated configurations saved to: {config_log_path}")
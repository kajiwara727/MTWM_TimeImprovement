# runners/file_load_runner.py
from .base_runner import BaseRunner
from utils import generate_config_hash
from reporting import save_comparison_summary # 専用のサマリー関数
import json
import os


class FileLoadRunner(BaseRunner):
    """
    設定ファイル (config.CONFIG_LOAD_FILE) からターゲット設定を読み込み、
    最適化を実行する専用のRunner。
    'random' モードで生成された 'random_configs.json' などを再実行するのに使う。
    """

    def run(self):
        targets_configs_to_run = [] # 実行すべき設定(複数)を格納するリスト
        
        # 1. Configから読み込むべきファイルパスを取得
        config_path = self.config.CONFIG_LOAD_FILE

        if not config_path:
            # パスが空文字やNoneの場合、エラー
            raise ValueError("CONFIG_LOAD_FILEが設定されていません。config.pyにファイルパスを指定してください。")

        # 2. JSON ファイルの読み込み
        try:
            print(f"Loading configuration from file: {config_path}...")
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f) # JSONをパースして辞書またはリストにする

            if not data:
                raise ValueError("設定ファイルが空です。")

            # 3. 読み込んだデータの構造を解析
            if isinstance(data, list) and len(data) > 0:
                # dataがリスト形式の場合
                if "targets" in data[0]:
                    # (A) 'random_configs.json' の形式 (run_name と targets を持つオブジェクトのリスト)
                    # [ {"run_name": "run_1", "targets": [...]},
                    #   {"run_name": "run_2", "targets": [...]}, ... ]
                    targets_configs_to_run = data
                elif "ratios" in data[0]:
                    # (B) シンプルなターゲット設定のリスト形式
                    # [ {"name": "T1", "ratios": [...]},
                    #   {"name": "T2", "ratios": [...]}, ... ]
                    # この場合、実行は1回だけとし、configのRUN_NAMEを流用
                    targets_configs_to_run.append(
                        {"run_name": self.config.RUN_NAME, "targets": data}
                    )
                else:
                    raise ValueError("設定ファイルの構造が無効です。ターゲットのリスト、またはランオブジェクトのリストが必要です。")

        # --- エラーハンドリング ---
        except FileNotFoundError:
            raise FileNotFoundError(f"設定ファイルが見つかりません: {config_path}")
        except json.JSONDecodeError:
            raise ValueError(
                f"JSONデコードエラー: {config_path}。ファイルが正しいJSON形式であることを確認してください。"
            )
        except Exception as e:
            raise RuntimeError(f"設定の読み込み中にエラーが発生しました: {e}")

        # 4. 読み込んだ結果が空でないかチェック
        if not targets_configs_to_run:
            raise ValueError("設定ファイルからターゲットが読み込まれませんでした。")

        print(
            f"Configuration successfully loaded. Found {len(targets_configs_to_run)} pattern(s) to run."
        )

        all_comparison_results = [] # 全実行結果を保存するリスト
        
        # 5. ベースとなる出力ディレクトリを決定
        #    (PermutationRunnerと同様、全実行結果をまとめる親ディレクトリ)
        base_output_dir = self._get_unique_output_directory_name(
            self.config.RUN_NAME, self.config.RUN_NAME + "_comparison"
        )
        os.makedirs(base_output_dir, exist_ok=True)
        print(f"All comparison results will be saved under: '{base_output_dir}/'")

        # 6. 読み込んだ全設定 (パターン) をループで実行
        for run_idx, run_data in enumerate(targets_configs_to_run):
            # run_data は (A) の形式 (例: {"run_name": "run_1", "targets": [...]})
            
            # JSONファイル内の "run_name" を使う。なければ連番
            run_name_prefix = run_data.get("run_name", f"Run_{run_idx+1}")
            targets_config_base = run_data["targets"] # 実行するターゲット設定

            print(
                f"\n{'='*20} Running Loaded Pattern {run_idx+1}/{len(targets_configs_to_run)} ({run_name_prefix}) {'='*20}"
            )

            # 7. 出力ディレクトリ名を決定
            base_run_name = run_name_prefix + f"_loaded"
            config_hash = generate_config_hash(
                targets_config_base, self.config.OPTIMIZATION_MODE, base_run_name
            )
            output_dir_name = self._get_unique_output_directory_name(
                config_hash, base_run_name
            )
            # 親ディレクトリ(base_output_dir)の下に作成
            output_dir = os.path.join(base_output_dir, output_dir_name)

            # 8. 単一最適化を実行
            (
                final_value,
                exec_time,
                total_ops,
                total_reagents,
                total_waste,
            ) = self._run_single_optimization(
                targets_config_base, output_dir, self.config.RUN_NAME
            )

            # 9. 結果をリストに保存
            all_comparison_results.append(
                {
                    "run_name": run_name_prefix,
                    "final_value": final_value,
                    "elapsed_time": exec_time,
                    "total_operations": total_ops,
                    "total_reagents": total_reagents,
                    "total_waste": total_waste,
                    "config": targets_config_base,
                    "objective_mode": self.config.OPTIMIZATION_MODE,
                }
            )

        # 10. 全実行が完了したら、比較用のサマリー関数を呼び出す
        save_comparison_summary(
            all_comparison_results, base_output_dir, self.config.OPTIMIZATION_MODE
        )
        print("\nAll comparison runs finished successfully.")
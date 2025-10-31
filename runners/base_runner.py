# runners/base_runner.py
import os
from abc import ABC, abstractmethod  # 抽象基底クラス(ABC)をインポート

# --- プロジェクトのコアモジュールをインポート ---
from core import (
    MTWMProblem,
    build_dfmm_forest,
    calculate_p_values_from_structure,
    OrToolsSolver,
)
from reporting.reporter import SolutionReporter
from reporting.analyzer import PreRunAnalyzer

class BaseRunner(ABC):  # 抽象基底クラス(ABC)を継承
    """
    全ての実行モード（ランナー）クラスの親となる抽象基底クラス。
    
    共通の設定(config)の保持と、中核となる単一最適化の実行フロー
    (_run_single_optimization) を提供します。
    """

    def __init__(self, config):
        """
        コンストラクタ。
        Configオブジェクトを受け取り、インスタンス変数として保持します。
        
        Args:
            config (Config): utils.config_loader.Config オブジェクト
        """
        self.config = config

    @abstractmethod  # このメソッドは「抽象メソッド」であることを示す
    def run(self):
        """
        実行モードのメインロジック。
        このメソッドは子クラス（例: StandardRunner）で必ず実装（オーバーライド）
        されなければなりません。
        """
        raise NotImplementedError

    def _get_unique_output_directory_name(self, config_hash, base_name_prefix):
        """
        実行結果を保存するための一意なディレクトリ名を生成します。
        もし同名のディレクトリが既に存在する場合は、末尾に _1, _2 ... と
        連番を振って重複を防ぎます。

        Args:
            config_hash (str): 設定のハッシュ値 (8文字分だけ使用)
            base_name_prefix (str): 実行名 (RUN_NAME)

        Returns:
            str: 一意なディレクトリ名 (例: "My_First_Run_eb8386bc")
        """
        # ベース名 = 実行名 + ハッシュ値の先頭8文字
        base_name = f"{base_name_prefix}_{config_hash[:8]}"
        output_dir = base_name
        counter = 1
        
        # os.path.isdir() で同名のディレクトリが存在するかチェック
        while os.path.isdir(output_dir):
            # 存在した場合、末尾に _(連番) を付けて再チェック
            output_dir = f"{base_name}_{counter}"
            counter += 1
        
        # 重複しないディレクトリ名が確定したら、それを返す
        return output_dir

    def _run_single_optimization(
        self, targets_config_for_run, output_dir, run_name_for_report
    ):
        """
        単一のターゲット設定セットに対して、最適化を実行する共通メソッドです。
        これがこのプロジェクトのメインワークフローです。
        
        Args:
            targets_config_for_run (list): 実行するターゲット設定のリスト
            output_dir (str): 結果を保存するディレクトリ名
            run_name_for_report (str): レポートに記載する実行名

        Returns:
            tuple: (final_value, elapsed_time, ops, reagents, total_waste)
                   サマリーレポート用に、最適化の結果（目的値、実行時間、各メトリクス）を返す
        """
        # --- 実行設定をコンソールに出力 ---
        print("\n--- Configuration for this run ---")
        print(f"Run Name: {run_name_for_report}")
        for target in targets_config_for_run:
            print(
                f"  - {target['name']}: Ratios = {target['ratios']}, Factors = {target['factors']}"
            )
        print(f"Optimization Mode: {self.config.OPTIMIZATION_MODE.upper()}")
        print("-" * 35 + "\n")

        # --- 1. DFMMアルゴリズムでツリー構造とP値を計算 ---
        # (core/dfmm.py)
        
        # 混合ツリーの構造（親子関係）を構築
        tree_structures = build_dfmm_forest(targets_config_for_run)
        # 構築したツリー構造に基づき、各ノードのP値（濃度計算の基準値）を計算
        p_value_maps = calculate_p_values_from_structure(
            tree_structures, targets_config_for_run
        )

        # --- 2. 最適化問題オブジェクトを生成 ---
        # (core/problem.py)
        
        # DFMMの結果(ツリー構造, P値)とターゲット設定を渡し、
        # ソルバーが扱う変数や共有可能性を定義した「問題オブジェクト」を生成
        problem = MTWMProblem(targets_config_for_run, tree_structures, p_value_maps)

        # --- 3. 出力ディレクトリを作成し、事前分析レポートを生成 ---
        # (reporting/analyzer.py)
        
        os.makedirs(output_dir, exist_ok=True)
        print(f"All outputs for this run will be saved to: '{output_dir}/'")
        
        # ソルバー実行「前」の分析レポート (ツリー構造やP値の妥当性確認) を生成
        analyzer = PreRunAnalyzer(problem, tree_structures)
        analyzer.generate_report(output_dir)

        # --- 4. Or-Toolsソルバーを初期化 ---
        # (or_tools_solver.py)
        
        # 問題オブジェクト(problem)と最適化モードを渡し、
        # Or-Toolsソルバーのインスタンスを作成 (この時点で制約がモデルに追加される)
        solver = OrToolsSolver(problem, objective_mode=self.config.OPTIMIZATION_MODE)

        # --- 5. 最適化を実行 ---
        # solve() メソッドを呼び出し、最適化計算を開始
        # best_model: OrToolsSolutionModel (解のラッパー)
        # final_value: 目的変数（例: 廃棄物量）の最小値
        # best_analysis: 解の分析結果 (辞書)
        # elapsed_time: 計算時間
        best_model, final_value, best_analysis, elapsed_time = solver.solve()

        # --- 6. SolutionReporterを初期化 ---
        # (reporting/reporter.py)
        
        # ソルバーが見つけた解(best_model)と問題定義(problem)を渡し、
        # 最終レポート（summary.txt や .png）を生成する準備
        reporter = SolutionReporter(
            problem,
            best_model,
            objective_mode=self.config.OPTIMIZATION_MODE,
            enable_visualization=self.config.ENABLE_VISUALIZATION # 可視化ON/OFF
        )

        # サマリーレポート用に、各メトリクスの初期値を None に設定
        ops = None
        reagents = None
        total_waste = None

        # --- 7. 結果に応じてレポートを生成 ---
        if best_model:
            # 解が見つかった場合 (best_model が None でない)
            
            # `best_analysis` は `solve` から取得済みのものを使用
            # summary.txt と mixing_tree_visualization.png を生成
            reporter.generate_full_report(final_value, elapsed_time, output_dir)

            # サマリーレポート用に、分析結果から各メトリクスを取得
            ops = best_analysis.get("total_operations")
            reagents = best_analysis.get("total_reagent_units")
            total_waste = best_analysis.get("total_waste")
        else:
            # 解が見つからなかった場合
            print("\n--- No solution found for this configuration ---")

        # 実行結果（目的値、時間、各メトリクス）を返す
        return final_value, elapsed_time, ops, reagents, total_waste
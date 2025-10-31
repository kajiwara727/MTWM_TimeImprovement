# runners/standard_runner.py

# 親クラスである BaseRunner をインポート
from .base_runner import BaseRunner
# 'auto' モードで factors を計算するために dfmm モジュールから関数をインポート
from core import find_factors_for_sum
# 出力ディレクトリ名を生成するために helpers モジュールから関数をインポート
from utils import generate_config_hash


class StandardRunner(BaseRunner):
    """
    'auto' または 'manual' モードという、基本的な単一の最適化実行を担当するクラス。
    BaseRunner の `run` メソッドを具体的に実装します。
    """

    def run(self):
        """
        'auto' / 'manual' モードの実行ロジック。
        """
        
        # 1. configからターゲット設定を取得
        # (Config.get_targets_config() がモードに応じて適切なリストを返す)
        targets_config_base = self.config.get_targets_config()

        # 2. モードに応じてコンソールにメッセージを表示
        mode_name = (
            "Using manually specified factors..."
            if self.config.MODE == "manual"
            else "Calculating factors automatically..."
        )
        print(mode_name)

        # 3. 'auto' モードの場合、各ターゲットの混合階層（factors）を自動で計算
        if self.config.MODE == "auto":
            for target in targets_config_base:
                # DFMMアルゴリズム(find_factors_for_sum)を使って、
                # 比率の合計値(sum(target["ratios"]))から
                # 因数(factors)のリストを探す
                factors = find_factors_for_sum(
                    sum(target["ratios"]), self.config.MAX_MIXER_SIZE
                )
                if factors is None:
                    # 因数が見つからない場合 (例: 合計値が素数でMAX_MIXER_SIZEより大きい)
                    # エラーを発生させて停止
                    raise ValueError(
                        f"Could not determine factors for {target['name']}."
                    )
                
                # 見つかった因数をターゲット設定の 'factors' キーに格納
                target["factors"] = factors

        # ('manual' モードの場合は、config.pyで指定された'factors'をそのまま使用する)

        # 4. 実行設定から一意のハッシュを生成し、出力ディレクトリ名を決定
        config_hash = generate_config_hash(
            targets_config_base, self.config.OPTIMIZATION_MODE, self.config.RUN_NAME
        )
        output_dir = self._get_unique_output_directory_name(
            config_hash, self.config.RUN_NAME
        )

        # 5. 準備が整った設定を使って、共通の単一最適化実行メソッドを呼び出す
        # (このメソッドは親クラス BaseRunner で定義されている)
        self._run_single_optimization(
            targets_config_base, output_dir, self.config.RUN_NAME
        )
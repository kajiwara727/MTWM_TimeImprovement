import config


class Config:
    """
    設定ファイル (config.py) から値を読み込み、アプリケーション全体で
    一元的に管理するためのクラス。
    これにより、設定へのアクセスが容易になり、コードの他の部分から
    設定ファイルの詳細を隠蔽します。
    
    他のファイルからは `from utils.config_loader import Config` のように呼び出し、
    `Config.MODE` や `Config.MAX_MIXER_SIZE` のようにアクセスします。
    """

    # --- config.py から主要な設定値をクラス属性として読み込む ---
    # `config.RUN_NAME` の値を `Config.RUN_NAME` にコピー
    RUN_NAME = config.RUN_NAME
    MODE = config.FACTOR_EXECUTION_MODE
    OPTIMIZATION_MODE = config.OPTIMIZATION_MODE
    CONFIG_LOAD_FILE = config.CONFIG_LOAD_FILE
    ENABLE_VISUALIZATION = config.ENABLE_VISUALIZATION

    MAX_CPU_WORKERS = config.MAX_CPU_WORKERS
    MAX_SHARING_VOLUME = config.MAX_SHARING_VOLUME
    MAX_LEVEL_DIFF = config.MAX_LEVEL_DIFF
    MAX_MIXER_SIZE = config.MAX_MIXER_SIZE
    ENABLE_FINAL_PRODUCT_SHARING = config.ENABLE_FINAL_PRODUCT_SHARING

    # --- 'random' モード用の設定を個別に読み込む ---
    RANDOM_T_REAGENTS = config.RANDOM_T_REAGENTS
    RANDOM_N_TARGETS = config.RANDOM_N_TARGETS
    RANDOM_K_RUNS = config.RANDOM_K_RUNS
    RANDOM_S_RATIO_SUM_SEQUENCE = config.RANDOM_S_RATIO_SUM_SEQUENCE
    RANDOM_S_RATIO_SUM_CANDIDATES = config.RANDOM_S_RATIO_SUM_CANDIDATES
    RANDOM_S_RATIO_SUM_DEFAULT = config.RANDOM_S_RATIO_SUM_DEFAULT

    @staticmethod
    def get_targets_config():
        """
        現在の実行モード (MODE) に応じて、config.py から適切な
        ターゲット設定リストを返します。
        
        静的メソッド(@staticmethod)なので、インスタンス化せずに
        `Config.get_targets_config()` のように呼び出せます。

        Returns:
            list: ターゲット設定のリスト (例: [{'name': 'T1', 'ratios': [1,2,3], ...}])

        Raises:
            ValueError: config.pyで未知のモードが指定されている場合に発生します。
        """
        # 現在のモードが 'auto' または 'auto_permutations' の場合
        if Config.MODE in ["auto", "auto_permutations"]:
            # 'auto'系モードの場合は、TARGETS_FOR_AUTO_MODE を使用
            return config.TARGETS_FOR_AUTO_MODE
        
        # 現在のモードが 'manual' の場合
        elif Config.MODE == "manual":
            # 'manual'モードの場合は、TARGETS_FOR_MANUAL_MODE を使用
            return config.TARGETS_FOR_MANUAL_MODE
        
        # 現在のモードが 'random' または 'file_load' の場合
        elif Config.MODE == "random" or Config.MODE == "file_load":
            # これらのモードではターゲット設定は動的に生成/ロードされるため、
            # このメソッドからは設定を返さない (空リストを返す)
            return []
        
        # 上記のいずれにも該当しない未知のモードの場合
        else:
            # エラーを発生させてプログラムを停止
            raise ValueError(
                f"Unknown FACTOR_EXECUTION_MODE in config.py: '{Config.MODE}'"
            )

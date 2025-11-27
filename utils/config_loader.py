# utils/config_loader.py
import config
import scenarios  # [NEW] シナリオファイルをインポート

class Config:
    # --- config.py から設定値を読み込む ---
    RUN_NAME = config.RUN_NAME
    MODE = config.FACTOR_EXECUTION_MODE
    OPTIMIZATION_MODE = config.OPTIMIZATION_MODE
    CONFIG_LOAD_FILE = config.CONFIG_LOAD_FILE
    ENABLE_VISUALIZATION = config.ENABLE_VISUALIZATION

    MAX_CPU_WORKERS = config.MAX_CPU_WORKERS
    MAX_TIME_PER_RUN_SECONDS = config.MAX_TIME_PER_RUN_SECONDS
    ABSOLUTE_GAP_LIMIT = config.ABSOLUTE_GAP_LIMIT
    MAX_SHARING_VOLUME = config.MAX_SHARING_VOLUME
    MAX_TOTAL_REAGENT_INPUT_PER_NODE = config.MAX_TOTAL_REAGENT_INPUT_PER_NODE
    MAX_LEVEL_DIFF = config.MAX_LEVEL_DIFF
    MAX_MIXER_SIZE = config.MAX_MIXER_SIZE
    PEER_NODE_LIMIT = config.PEER_NODE_LIMIT
    ENABLE_FINAL_PRODUCT_SHARING = config.ENABLE_FINAL_PRODUCT_SHARING

    RANDOM_T_REAGENTS = config.RANDOM_T_REAGENTS
    RANDOM_N_TARGETS = config.RANDOM_N_TARGETS
    RANDOM_K_RUNS = config.RANDOM_K_RUNS
    RANDOM_S_RATIO_SUM_SEQUENCE = config.RANDOM_S_RATIO_SUM_SEQUENCE
    RANDOM_S_RATIO_SUM_CANDIDATES = config.RANDOM_S_RATIO_SUM_CANDIDATES
    RANDOM_S_RATIO_SUM_DEFAULT = config.RANDOM_S_RATIO_SUM_DEFAULT

    @staticmethod
    def get_targets_config():
        """モードに応じて scenarios.py からターゲット設定を取得します"""
        if Config.MODE in ["auto", "auto_permutations"]:
            return scenarios.TARGETS_FOR_AUTO_MODE  # [MODIFIED]
        
        elif Config.MODE == "manual":
            return scenarios.TARGETS_FOR_MANUAL_MODE  # [MODIFIED]
        
        elif Config.MODE == "random" or Config.MODE == "file_load":
            return []
        
        else:
            raise ValueError(f"Unknown FACTOR_EXECUTION_MODE: '{Config.MODE}'")
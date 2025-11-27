# 実行名を定義します。出力ディレクトリの名前の一部として使用されます。
RUN_NAME = "test"

# 実行モード: 'manual', 'auto', 'auto_permutations', 'random', 'file_load'
FACTOR_EXECUTION_MODE = "random"

# 最適化の目的: "waste", "operations", "reagents"
OPTIMIZATION_MODE = "waste"

# --- 出力設定 ---
ENABLE_VISUALIZATION = True # True or False
CONFIG_LOAD_FILE = "random_configs.json"

# --- 制約条件 (ソルバーの挙動制御) ---
MAX_CPU_WORKERS = None
MAX_TIME_PER_RUN_SECONDS = None
ABSOLUTE_GAP_LIMIT = 0.99
MAX_SHARING_VOLUME = None
MAX_SHARED_INPUTS = None
MAX_TOTAL_REAGENT_INPUT_PER_NODE = None
MAX_LEVEL_DIFF = None
MAX_MIXER_SIZE = 5
PEER_NODE_LIMIT = "half_p_group"
ENABLE_FINAL_PRODUCT_SHARING = False

# --- 'random' モード用パラメータ ---
RANDOM_N_TARGETS = 3
RANDOM_T_REAGENTS = 3
RANDOM_K_RUNS = 10
RANDOM_S_RATIO_SUM_DEFAULT = 18

# --- 混合比和の生成ルール（以下のいずれか1つが使用されます） ---
# 以下の設定は、`runners/random_runner.py` によって上から順に評価され、
# 最初に有効な（空でない）設定が1つだけ採用されます。

# オプション1: 固定シーケンス
# `RANDOM_N_TARGETS` と要素数を一致させる必要があります。
# (例: [18, {'base_sum': 18, 'multiplier': 5}, 18, 24])
# これが空でないリストの場合、この設定が使用されます。
RANDOM_S_RATIO_SUM_SEQUENCE = [
   #  18, {'base_sum': 18, 'multiplier': 5}, 18
]

# オプション2: 候補リストからのランダム選択
# `RANDOM_S_RATIO_SUM_SEQUENCE` が空のリストの場合、こちらが評価されます。
# (例: [18, 24, 30, 36])
# これが空でないリストの場合、ターゲットごとにこのリストからランダムに値が選ばれます。
RANDOM_S_RATIO_SUM_CANDIDATES = [
    # 18, 24, 30, 36
]
# 実行名を定義します。出力ディレクトリの名前の一部として使用されます。
# 例: "My_First_Run" -> "My_First_Run_xxxx" のようなディレクトリが生成される
RUN_NAME = "3-3_135_TimeCompare"

# 混合ツリーの階層構造（factors）を決定するモードを選択します。
# 'manual': TARGETS_FOR_MANUAL_MODE で定義された factors を手動で設定します。
# 'auto': 各ターゲットの ratios の合計値から factors を自動計算します。
# 'auto_permutations': 'auto' で計算された factors の全順列を試し、最適な階層構造を探します。
# 'random': RANDOM_... 設定に基づいてランダムなシナリオを複数回実行します。
# 'file_load': CONFIG_LOAD_FILEで指定されたJSONファイルから設定を読み込みます。
FACTOR_EXECUTION_MODE = "file_load"
# 最適化の目的を設定します。
# "waste": 廃棄物量の最小化を目指します。（最も重要な目的）
# "operations": 混合操作の総回数の最小化を目指します。（プロセス簡略化）
# "reagents": 総試薬使用量の最小化を目指します。（コスト削減）
OPTIMIZATION_MODE = "waste"

# --- 出力設定 ---
# Trueに設定すると、最適化完了後に混合ツリーの可視化グラフ (PNG画像) を生成します。
# Falseに設定すると、グラフ生成をスキップし、処理時間を短縮できます。
ENABLE_VISUALIZATION = False

# 'file_load' モードで使用する設定ファイル名を指定します。
# ランダム実行で生成したファイル名 (例: "manual-check_eb8386bc_1/random_configs.json") を設定すると、
# そのJSONファイルに記録されたシナリオを再実行できます。
CONFIG_LOAD_FILE = "random_configs.json"

# --- 制約条件 (ソルバーの挙動に大きく影響します) ---

# ソルバーが使用するCPUコア（ワーカー）の最大数を設定します。
# 共有マシンの場合は、 2 や 4 などの低い値に設定することを推奨します。
# None に設定すると、Or-Toolsが利用可能な全コアを使用します。
MAX_CPU_WORKERS = 32

# 追加: (1回の実行（1パターン）あたりの最大計算時間（秒）)
# ソルバーが最適性の証明などでスタックしても、ここで設定した秒数が経過すると
# 自動的に打ち切られ、次のパターンの計算に進みます。
# None または 0 に設定すると、時間無制限になります。
MAX_TIME_PER_RUN_SECONDS = 2000

# 追加: (早期停止のための「絶対ギャップ」)
# 目的（廃棄物など）は整数であるため、 0.99 のような「1未満」の値を設定すると、
# (最良解) - (下限値) が 0.99 を下回った瞬間に停止します。
# (例: 最良解 3.0、下限値 2.01 の時点で停止)
# これにより、最適性の証明にかかる時間を短縮できます。
# None または 0 に設定すると、この機能は無効になります。
ABSOLUTE_GAP_LIMIT = 0.99

# ノード間で共有（中間液を融通）できる液量の最大値を設定します。
# 例えば 1 に設定すると、共有は「1単位ずつ」に制限されます。
# Noneの場合は無制限です。
MAX_SHARING_VOLUME = 2

# 例: 2 に設定すると、3種類以上の異なる中間液を混ぜる解を禁止します。
# None に設定すると無制限になります。
MAX_SHARED_INPUTS = 3

# 追加: (ノード当たりの純粋試薬投入量の合計上限)
# DFMMノード一つに投入できる純粋試薬 (Reagent) の合計量の上限を設定します。
# ノードの容量 (MAX_MIXER_SIZE) と比較して小さい値を設定すると、
# 探索空間を制限し、実行時間の短縮に役立つ場合があります。
# None または 0 に設定すると、制約は適用されません。
MAX_TOTAL_REAGENT_INPUT_PER_NODE = None

# 中間液を共有する際の、供給元と供給先の階層レベル（level）の差の最大値を設定します。
# 例えば 2 に設定すると、level 3 のノードは level 1 のノードにしか供給できません。
# Noneの場合は無制限です。
MAX_LEVEL_DIFF = None

# 1回の混合操作で使用できるミキサーの最大容量（入力の合計値）を設定します。
# これはDFMMアルゴリズムで混合ツリーの階層を決定する際の因数の最大値にもなります。
# 例えば 5 に設定すると、[3, 3, 2] はOKですが [7, 2] はNG (7が5を超えるため) となります。
MAX_MIXER_SIZE = 5

# ペア(R)ノードの生成数（変数）の上限を設定します。
# "half_p_group": (推奨/ご要望) P値が同じノードグループごとに、そのノード数の半分（切り捨て）を上限としてペアを生成します。
# "unlimited": (従来通り) P値が一致する全ての1:1組み合わせを探索します。
# "half_targets": (旧案) 全体で、ターゲット数の半分を上限とします。
# 整数 (例: 50): 具体的な数値で全体の上限を設定します。
PEER_NODE_LIMIT = "half_p_group"

# Trueに設定すると、Level 0 のノード (最終ターゲット液) も
# 他のノードの材料として共有することを許可します。
ENABLE_FINAL_PRODUCT_SHARING = False

# --- 'random' モード用設定 ---
# (RANDOM_SETTINGS 辞書を廃止し、トップレベルの変数に)

# ランダムシナリオにおけるターゲット（目標混合液）の数 (例: 3ターゲット)
RANDOM_N_TARGETS = 2
# ランダムシナリオにおける試薬の種類数 (例: 3種類)
RANDOM_T_REAGENTS = 3
# 生成・実行するランダムシナリオの総数 (例: 100回)
RANDOM_K_RUNS = 10

# オプション3: デフォルト値
# 上記の `SEQUENCE` と `CANDIDATES` が両方とも空のリストの場合、
# このデフォルト値が全てのターゲットで使用されます。
RANDOM_S_RATIO_SUM_DEFAULT = 135

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


# --- 'auto' / 'auto_permutations' モード用設定 ---
# 'auto'系モードでは、'factors' (混合階層) を指定する必要はありません。
# 'ratios' (混合比率) のみ定義します。
TARGETS_FOR_AUTO_MODE = [
    # 試薬数削減確認
    {'name': 'Target 1', 'ratios': [3,10,1,4]},
    {'name': 'Target 2', 'ratios': [6,3,5,4]},

    # Simple
    # {'name': 'Target 1', 'ratios': [2,11,5]},
    # {'name': 'Target 2', 'ratios': [12,5,1]},
    # {'name': 'Target 3', 'ratios': [5,6,14]}

     # すべて12:12:1の場合
    # {'name': 'Target 1', 'ratios': [12,12,1]},
    # {'name': 'Target 2', 'ratios': [12,12,1]},
    # {'name': 'Target 3', 'ratios': [12,12,1]}

    # すべて97:97:6の場合
    # {'name': 'Target 1', 'ratios': [97,97,6]},
    # {'name': 'Target 2', 'ratios': [97,97,6]},
    # {'name': 'Target 3', 'ratios': [97,97,6]}

     # すべて49:49:2の場合
    # {'name': 'Target 1', 'ratios': [49,49,2]},
    # {'name': 'Target 2', 'ratios': [49,49,2]},
    # {'name': 'Target 3', 'ratios': [49,49,2]}

    # 49:98:147
    # {'name': 'Target 1', 'ratios': [26,10,13]},
    # {'name': 'Target 2', 'ratios': [53,20,25]},
    # {'name': 'Target 3', 'ratios': [79,30,38]},

    # 49:98:147_Second
    # {'name': 'Target 1', 'ratios': [23,13,13]},
    # {'name': 'Target 2', 'ratios': [46,27,25]},
    # {'name': 'Target 3', 'ratios': [69,40,38]},

    # 49:98:147_Third
    # {'name': 'Target 1', 'ratios': [19,17,13]},
    # {'name': 'Target 2', 'ratios': [40,33,25]},
    # {'name': 'Target 3', 'ratios': [59,50,38]},

    # TimeTest
    # {'name': 'Target 1', 'ratios': [2, 12,3,1]},
    # {'name': 'Target 2', 'ratios': [5,3,4,6]},
    # {'name': 'Target 3', 'ratios': [7,3,7,1]},
    # {'name': 'Target 4', 'ratios': [9,2,6,1]},
    # {'name': 'Target 5', 'ratios': [13,1,1,3]},

    # {'name': 'Target 2', 'ratios': [93,21,21]},
    # {'name': 'Target 3', 'ratios': [46,74,15]},
    # {'name': 'Target 3', 'ratios': [3, 5, 10]},
    # {'name': 'Target 4', 'ratios': [7, 7, 4]},
    # {'name': 'Target 2', 'ratios': [60, 25, 5]},
    # {'name': 'Target 4', 'ratios': [6, 33, 36]},
    # {'name': 'Target 1', 'ratios': [102, 26, 3, 3, 122]},
    # {'name': 'Target 1', 'ratios': [15, 18, 42]}
]

# --- 'manual' モード用設定 ---
# 'manual' モードでは、'ratios' に加えて 'factors' を明示的に指定する必要があります。
# 'factors' の積は、'ratios' の合計値と一致する必要があります。
# また、'factors' の各要素は MAX_MIXER_SIZE 以下でなければなりません。
TARGETS_FOR_MANUAL_MODE = [
    # {'name': 'Target 1', 'ratios': [23,13,13]},
    # {'name': 'Target 2', 'ratios': [46,27,25]},
    # {'name': 'Target 3', 'ratios': [69,40,38]},

    # 49:98:147_Second
    # {'name': 'Target 1', 'ratios': [23,13,13], 'factors': [7,7]},
    # {'name': 'Target 2', 'ratios': [46,27,25], 'factors': [7,2,7]},
    # {'name': 'Target 3', 'ratios': [69,40,38], 'factors': [7,3,7]},

    # {'name': 'Target 1', 'ratios': [6, 33, 15], 'factors': [3, 3, 3, 2]},
    # {'name': 'Target 1', 'ratios': [2, 3, 7], 'factors': [3, 2, 2]},
    # {'name': 'Target 2', 'ratios': [1, 5, 6], 'factors': [3, 2, 2]},
    # {'name': 'Target 3', 'ratios': [4, 3, 5], 'factors': [3, 2, 2]},
    # {'name': 'Target 3', 'ratios': [4, 5, 9], 'factors': [3, 3, 2]},
    # {'name': 'Target 3', 'ratios': [3, 5, 10], 'factors': [3, 3, 2]},
    # {'name': 'Target 4', 'ratios': [7, 7, 4], 'factors': [3, 3, 2]},
    # {'name': 'Target 2', 'ratios': [60, 25, 5], 'factors': [5, 3, 3, 2]},
    # {'name': 'Target 3', 'ratios': [5, 6, 14], 'factors': [5, 5]},
    # {'name': 'Target 4', 'ratios': [6, 33, 36], 'factors': [3, 5, 5]},
    # {'name': 'Target 1', 'ratios': [102, 26, 3, 3, 122], 'factors': [4, 4, 4, 4]},
    # {"name": "Target 1", "ratios": [2, 11, 5], "factors": [3, 3, 2]},
    # {'name': 'Target 2', 'ratios': [12, 5, 1], 'factors': [3, 3, 2]},
    # {'name': 'Target 3', 'ratios': [5, 6, 14], 'factors': [5, 5]},
    # {'name': 'Target 1', 'ratios': [10, 55, 25], 'factors': [5, 3, 3, 2]},
    # {"name": "Target 2", "ratios": [60, 25, 5], "factors": [5, 3, 3, 2]},
    # {'name': 'Target 3', 'ratios': [15, 18, 42], 'factors': [3, 5, 5]}
]

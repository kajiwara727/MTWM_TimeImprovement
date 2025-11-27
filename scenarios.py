# --- 'auto' / 'auto_permutations' モード用設定 ---
# 'auto'系モードでは、'factors' (混合階層) を指定する必要はありません。
# 'ratios' (混合比率) のみ定義します。
TARGETS_FOR_AUTO_MODE = [
    # 試薬数削減確認
    # {'name': 'Target 1', 'ratios': [3,10,1,4]},
    # {'name': 'Target 2', 'ratios': [6,3,5,4]},

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
    {'name': 'Target 1', 'ratios': [19,17,13]},
    {'name': 'Target 2', 'ratios': [40,33,25]},
    {'name': 'Target 3', 'ratios': [59,50,38]},

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

import json
import hashlib
import random
import re
import math
from functools import reduce

# --- キー生成・解析関数 (docstring追加) ---

# グラフノードや共有キーの識別子として使う接頭辞（プレフィックス）を定義
KEY_INTRA_PREFIX = "l"  # ツリー内(Intra-tree)共有キーの接頭辞
KEY_INTER_PREFIX = "t"  # ツリー間(Inter-tree)共有キーの接頭辞
KEY_PEER_PREFIX = "R_idx"  # ピア(R)ノード共有キーの接頭辞


def create_dfmm_node_name(target_idx, level, node_idx):
    """DFMMノードのグローバル名（全体で一意な名前）を生成します。

    Args:
        target_idx (int): ターゲットのインデックス (例: 0)。
        level (int): ノードの階層レベル (例: 1)。
        node_idx (int): レベル内でのノードのインデックス (例: 0)。

    Returns:
        str: グローバルノード名 (例: 'mixer_t0_l1_k0')。
    """
    # f-stringを使って、各インデックスを特定のフォーマットに整形して返す
    return f"mixer_t{target_idx}_l{level}_k{node_idx}"


def create_intra_key(level, node_idx):
    """ツリー内共有キーの本体部分を生成します。
       ('from_' プレフィックスは含まない)

    Args:
        level (int): 供給元ノードのレベル。
        node_idx (int): 供給元ノードのインデックス。

    Returns:
        str: 内部共有キー (例: 'l1k0')。
    """
    # ツリー内共有は、同じターゲットツリー内での共有なので、target_idxは不要
    return f"{KEY_INTRA_PREFIX}{level}k{node_idx}"


def create_inter_key(target_idx, level, node_idx):
    """ツリー間共有キーの本体部分を生成します。
       ('from_' プレフィックスは含まない)

    Args:
        target_idx (int): 供給元ノードのターゲットインデックス。
        level (int): 供給元ノードのレベル。
        node_idx (int): 供給元ノードのインデックス。

    Returns:
        str: 外部共有キー (例: 't0_l1k0')。
    """
    # どのツリーからの供給かを識別するため、target_idxが含まれる
    return f"{KEY_INTER_PREFIX}{target_idx}_l{level}k{node_idx}"


def create_peer_key(peer_idx):
    """ピア(R)ノード共有キーの本体部分を生成します。
       ('from_' プレフィックスは含まない)

    Args:
        peer_idx (int): ピア(R)ノードのインデックス。

    Returns:
        str: ピア共有キー (例: 'R_idx0')。
    """
    return f"{KEY_PEER_PREFIX}{peer_idx}"


def parse_sharing_key(key_str_no_prefix):
    """
    共有キー文字列 ('from_' を除いた本体部分) を解析し、
    供給元の種類とインデックス情報を辞書で返します。

    Args:
        key_str_no_prefix (str): 'from_' を除いたキー文字列 (例: 'R_idx0', 't0_l1k0', 'l1k0')。

    Returns:
        dict: 解析結果。キーは 'type' ('PEER', 'DFMM', 'INTRA') と、
              タイプに応じたインデックス ('idx', 'target_idx', 'level', 'node_idx')。

    Raises:
        ValueError: 未知のキー形式の場合。
    """
    # 1. ピア(R)ノードのキーかチェック (例: 'R_idx0')
    if key_str_no_prefix.startswith(KEY_PEER_PREFIX):
        # 'R_idx' の部分を取り除き、残った数値(インデックス)を整数に変換
        return {
            "type": "PEER",
            "idx": int(key_str_no_prefix.replace(KEY_PEER_PREFIX, "")),
        }

    # 2. ツリー間(Inter)共有キーかチェック (例: 't0_l1k0')
    elif key_str_no_prefix.startswith(KEY_INTER_PREFIX):
        # 正規表現(re.match)でパターンに一致するか確認
        # r"t(\d+)_l(\d+)k(\d+)" は以下のパターンを探す
        #   t: 't'という文字
        #   (\d+): 1桁以上の数字（これが group(1) = target_idx になる）
        #   _l: '_l'という文字
        #   (\d+): 1桁以上の数字（これが group(2) = level になる）
        #   k: 'k'という文字
        #   (\d+): 1桁以上の数字（これが group(3) = node_idx になる）
        match = re.match(r"t(\d+)_l(\d+)k(\d+)", key_str_no_prefix)
        if match:
            # マッチした場合、キャプチャしたグループを辞書に格納
            return {
                "type": "DFMM",  # ツリー間共有の供給元はDFMMノード
                "target_idx": int(match.group(1)),
                "level": int(match.group(2)),
                "node_idx": int(match.group(3)),
            }

    # 3. ツリー内(Intra)共有キーかチェック (例: 'l1k0')
    elif key_str_no_prefix.startswith(KEY_INTRA_PREFIX):
        # 正規表現でパターンに一致するか確認 (t(\d+)_ がないパターン)
        match = re.match(r"l(\d+)k(\d+)", key_str_no_prefix)
        if match:
            # マッチした場合、キャプチャしたグループを辞書に格納
            return {
                "type": "INTRA",
                "level": int(match.group(1)),
                "node_idx": int(match.group(2)),
            }

    # 4. どのパターンにも一致しなかった場合
    raise ValueError(f"Unknown sharing key format: {key_str_no_prefix}")

def _calculate_gcd_for_list(numbers):
    """リスト内のすべての数値の最大公約数（GCD）を計算します。"""
    if not numbers:
        return 1
    # reduceを使ってリスト全体にmath.gcdを適用
    # (例: gcd(gcd(n1, n2), n3), ...)
    return reduce(math.gcd, numbers)

def generate_config_hash(targets_config, mode, run_name):
    """
    実行設定（ターゲット設定、モード、実行名）から一意のMD5ハッシュ値を計算します。
    これにより、同じ設定での実行を識別したり、一意な出力ディレクトリ名を作成したりできます。

    Args:
        targets_config (list): ターゲット設定のリスト。
        mode (str): 実行モード (例: 'auto', 'waste')。
        run_name (str): 実行名 (例: 'My_First_Run')。

    Returns:
        str: MD5ハッシュ値 (16進数文字列)。
    """
    # 辞書やリストの順序が変わっても同じハッシュが生成されるよう、
    # json.dumpsでシリアライズ(文字列化)する際に `sort_keys=True` を指定
    config_str = json.dumps(targets_config, sort_keys=True)
    
    # 実行名、シリアライズした設定、モード名をハイフンで連結
    full_string = f"{run_name}-{config_str}-{mode}"
    
    # MD5ハッシュオブジェクトを作成
    hasher = hashlib.md5()
    
    # 文字列をUTF-8エンコードしてハッシュを更新
    hasher.update(full_string.encode("utf-8"))
    
    # 16進数文字列としてハッシュ値を取得
    return hasher.hexdigest()


def generate_random_ratios(reagent_count, ratio_sum, max_retries=100):
    """
    指定された合計値(ratio_sum)になる、指定された個数(reagent_count)の
    0を含まないランダムな整数のリストを生成します。
    (例: reagent_count=3, ratio_sum=18 -> [2, 11, 5])
    
    生成されたリストの最大公約数(GCD)が1になる（既約である）ことを保証しようと試みます。

    Args:
        reagent_count (int): 生成する数値の個数 (試薬の種類の数)。
        ratio_sum (int): 目標とする合計値。
        max_retries (int, optional): GCD=1の比率を見つけるための最大試行回数。

    Returns:
        list: 0を含まず、合計が ratio_sum になり、GCDが1である（可能性が高い）整数のリスト。
    
    Raises:
        ValueError: 合計値が試薬の数より少ない場合、または最大試行回数内に
                    GCD=1の比率が見つからなかった場合。
    """
    # 0を含まないため、合計値は最低でも試薬の数と同じでなければならない
    if ratio_sum < reagent_count:
        raise ValueError(
            f"Ratio sum ({ratio_sum}) cannot be less than the number of reagents ({reagent_count})."
        )

    # GCDが1になるまで、または最大リトライ回数に達するまでループ
    for _ in range(max_retries):
        # ロジック:
        # 合計値 18, 試薬数 3 の場合:
        # 1. 1〜17 (ratio_sum - 1) の範囲から、2つ (reagent_count - 1) の「仕切り」をランダムに選ぶ
        #    例: [5, 12]
        # 2. 仕切りをソートする (上記例では既にソート済み)
        # 3. 0と仕切り、仕切り同士、最後の仕切りと18の「間」を計算する
        #    (5 - 0)   -> 5
        #    (12 - 5)  -> 7
        #    (18 - 12) -> 6
        # 4. 結果: [5, 7, 6] (合計18, 0を含まない)
        
        # 1〜(ratio_sum-1) の範囲から、(reagent_count-1) 個のユニークな数値をランダムに選ぶ
        dividers = sorted(random.sample(range(1, ratio_sum), reagent_count - 1))

        ratios = []
        last_divider = 0 # 最初の仕切りは 0 とする
        
        # 選ばれた仕切りを順番に処理
        for d in dividers:
            ratios.append(d - last_divider) # 1つ前の仕切りとの差をリストに追加
            last_divider = d # 1つ前の仕切りを更新
            
        # 最後の仕切りと、合計値(ratio_sum)との差をリストに追加
        ratios.append(ratio_sum - last_divider)

        # --- GCDチェックを追加 ---
        if _calculate_gcd_for_list(ratios) == 1:
            return ratios # GCDが1ならループを抜けて結果を返す
        # --- ここまで ---

    # 最大リトライ回数に達してもGCD=1が見つからなかった場合
    raise ValueError(
        f"Could not find a set of ratios with GCD=1 for sum {ratio_sum} (reagents={reagent_count}) after {max_retries} attempts."
    )
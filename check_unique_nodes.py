import math
import sys
import os
import copy

# プロジェクトルートへのパスを通す (main.pyと同じ階層に置く想定)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.algorithm.dfmm import find_factors_for_sum
from scenarios import TARGETS_FOR_AUTO_MODE, TARGETS_FOR_MANUAL_MODE

# 設定: どちらのシナリオをチェックするか ("auto", "manual", "all")
CHECK_MODE = "all" 
MAX_MIXER_SIZE = 5  # Autoモードでのfactor計算用

def analyze_unique_reagent_allocation(target_config):
    """
    ターゲット設定を受け取り、DFMMロジックに従ってツリーを構築しつつ、
    各ノードの試薬割り当てが「一意に決まるか」を判定する。
    """
    name = target_config.get('name', 'Unknown Target')
    ratios = target_config['ratios']
    factors = target_config.get('factors')

    print(f"\n{'='*60}")
    print(f" Analysis for: {name}")
    print(f" Ratios: {ratios}")
    print(f" Factors: {factors}")
    print(f"{'='*60}")

    if not factors:
        print("Error: Factors are missing for this target.")
        return

    num_levels = len(factors)
    values_to_process = list(ratios)
    child_node_ids = [] # (level, index) のリスト

    # 下のレベルから上のレベルへシミュレーション
    for level in range(num_levels - 1, -1, -1):
        current_factor = factors[level]
        
        # 1. このレベルでの計算
        level_remainders = [v % current_factor for v in values_to_process]
        level_quotients = [v // current_factor for v in values_to_process]
        
        total_inputs = sum(level_remainders) + len(child_node_ids)
        num_nodes = math.ceil(total_inputs / current_factor) if total_inputs > 0 else 0
        
        # 試薬の種類数を確認 (値が >0 の試薬が何種類あるか)
        active_reagents_indices = [i for i, val in enumerate(level_remainders) if val > 0]
        num_active_reagents_types = len(active_reagents_indices)
        
        # このレベルで「試薬を受け入れる必要がある（空きがある）」ノードの数
        # (子ノードの分配はラウンドロビンで決定的とするため、各ノードの空き容量は計算可能)
        nodes_needing_reagents = []
        node_capacities = []
        
        # ノードごとの空き容量を計算
        for k in range(num_nodes):
            # 子ノードの数: child_node_ids をラウンドロビンで分配した場合の数を計算
            # child_node_ids の長さ L, ノード数 N の場合
            # k番目のノードが受け取る子の数は: L // N + (1 if k < L % N else 0)
            if num_nodes > 0:
                num_children = (len(child_node_ids) // num_nodes) + (1 if k < (len(child_node_ids) % num_nodes) else 0)
            else:
                num_children = 0
            
            slots_needed = current_factor - num_children
            node_capacities.append(slots_needed)
            
            if slots_needed > 0:
                nodes_needing_reagents.append(k)

        print(f"\n[Level {level}] (Factor: {current_factor})")
        print(f"  - Reagents to add (Remainders): {level_remainders} (Total: {sum(level_remainders)})")
        print(f"  - Nodes at this level: {num_nodes}")
        
        # --- 判定ロジック ---
        for k in range(num_nodes):
            node_name = f"Node_l{level}_k{k}"
            slots_needed = node_capacities[k]
            
            is_unique = False
            reason = ""

            # 条件1: 空き容量が0 (試薬は [0, 0, ...])
            if slots_needed == 0:
                is_unique = True
                reason = "Full with children (Capacity 0)"

            # 条件2: このレベルで試薬を受け取るノードが自分だけ (余り全てを受け取る)
            elif len(nodes_needing_reagents) == 1 and k in nodes_needing_reagents:
                is_unique = True
                reason = "Sole receiver at this level"

            # 条件3: 投入すべき試薬の種類が1種類のみ (空き容量をその試薬で埋める)
            elif num_active_reagents_types <= 1:
                is_unique = True
                reason = "Mono-reagent source (Only 1 type available)"
            
            # 判定結果の表示
            status_icon = "✅ UNIQUE" if is_unique else "⚠️ AMBIGUOUS"
            print(f"  {node_name:<15}: {status_icon} | Slots needed: {slots_needed} | {reason}")
            
            if not is_unique:
                print(f"      -> Must decide how to distribute: {level_remainders}")

        # 次のループへの準備
        child_node_ids = [(level, k) for k in range(num_nodes)]
        values_to_process = level_quotients

def prepare_targets():
    """scenarios.py からターゲットリストを作成する"""
    targets_to_check = []

    # 1. Manual Mode Targets (factorsが既に定義されている)
    if CHECK_MODE in ["manual", "all"]:
        print(f"Loading {len(TARGETS_FOR_MANUAL_MODE)} manual targets...")
        targets_to_check.extend(copy.deepcopy(TARGETS_FOR_MANUAL_MODE))

    # 2. Auto Mode Targets (factorsを計算する必要がある)
    if CHECK_MODE in ["auto", "all"]:
        print(f"Loading {len(TARGETS_FOR_AUTO_MODE)} auto targets...")
        auto_targets = copy.deepcopy(TARGETS_FOR_AUTO_MODE)
        
        for t in auto_targets:
            # factors がなければ計算して追加
            if 'factors' not in t:
                s = sum(t['ratios'])
                # core.algorithm.dfmm の関数を使用
                f = find_factors_for_sum(s, MAX_MIXER_SIZE)
                if f is None:
                    print(f"Skipping {t['name']}: Could not find factors for sum {s}")
                    continue
                t['factors'] = f
            targets_to_check.append(t)
            
    return targets_to_check

if __name__ == "__main__":
    print("--- Checking Reagent Allocation Uniqueness from scenarios.py ---")
    
    # ターゲットリストの準備
    config = prepare_targets()
    
    if not config:
        print("No targets found to check. Please check scenarios.py or CHECK_MODE.")
    else:
        # 各ターゲットについて分析を実行
        for target in config:
            analyze_unique_reagent_allocation(target)
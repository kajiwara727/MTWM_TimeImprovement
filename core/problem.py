import itertools
import math
from collections import defaultdict
from utils.config_loader import Config

from utils.helpers import (
    create_intra_key,
    create_inter_key,
    create_peer_key,
)

class MTWMProblem:

    def __init__(self, targets_config, tree_structures, p_value_maps):
        self.targets_config = targets_config
        self.num_reagents = len(targets_config[0]["ratios"]) if targets_config else 0
        self.tree_structures = tree_structures
        self.p_value_maps = p_value_maps
        self.forest = self._define_base_variables()
        self.peer_nodes = self._define_peer_mixing_nodes()
        self.potential_sources_map = self._precompute_potential_sources_v2()
        self._define_sharing_variables()

    def _define_base_variables(self):
        """
        混合ノードの「骨格」のみを定義します。
        変数の実体は OrToolsSolver が作成します。
        """
        forest_data = []
        for target_idx, tree_structure in enumerate(self.tree_structures):
            tree_data = {}
            levels = sorted({lvl for lvl, _ in tree_structure.keys()})

            for level in levels:
                nodes_at_level = sorted(
                    [
                        node_idx
                        for lvl_node, node_idx in tree_structure.keys()
                        if lvl_node == level
                    ]
                )
                level_nodes = []
                for node_idx in nodes_at_level:
                    # ★ プレースホルダーを削除し、空の辞書のみを追加
                    # この辞書には後に _define_sharing_variables で
                    # "intra_sharing_vars" と "inter_sharing_vars" が追加されます。
                    level_nodes.append({})

                tree_data[level] = level_nodes
            forest_data.append(tree_data)
        return forest_data

    def _define_peer_mixing_nodes(self):
        """
        [変更]
        P値が一致する中間ノードのペア(1:1混合)を定義します。
        config.PEER_NODE_LIMIT の設定に基づき、生成ロジックを変更します。
        
        - "half_p_group": P値グループごとにノード数の半分のペアを生成。
        - "half_targets", 整数, "unlimited": 全ノードの組み合わせから全体の上限まで生成。
        """
        print("Defining potential peer-mixing nodes (1:1 mix combinations)...")
        peer_nodes = [] # 結果のリスト

        # --- 1. config からモードと上限値 (limit) を決定 ---
        limit_config = "half_targets" # config.py にない場合のデフォルト
        if hasattr(Config, "PEER_NODE_LIMIT"):
            limit_config = Config.PEER_NODE_LIMIT

        num_targets = len(self.targets_config)
        global_limit = float('inf') # 全体の上限

        if limit_config == "half_p_group":
            print("  -> Mode: 'half_p_group'. Limiting peers per P-value group.")
            # このモードの場合、global_limit は使わず、グループごとに計算する
        else:
            if isinstance(limit_config, int):
                global_limit = limit_config
            elif limit_config == "half_targets":
                global_limit = math.floor(num_targets / 2) if num_targets > 0 else 0
            # "unlimited" または None の場合は float('inf') のまま

            print(f"  -> Mode: Global Limit. Config='{limit_config}' (Resolved Global Limit: {global_limit})")
            if global_limit == 0:
                print("  -> Global peer node limit is 0. Skipping peer node generation.")
                return []

        # --- 2. 全てのDFMMノード（L>0、非リーフ）を収集 ---
        all_dfmm_nodes_info = {} # { node_id: (p_val, f_val), ... }
        
        for target_idx, tree in enumerate(self.forest):
            for level, nodes in tree.items():
                if level == 0:
                    continue
                for node_idx, node in enumerate(nodes):
                    node_id = (target_idx, level, node_idx)
                    p_val = self.p_value_maps[target_idx].get((level, node_idx))
                    if p_val is None:
                        continue
                        
                    f_val = self.targets_config[target_idx]["factors"][level]
                    # リーフノード (P==F) は除外
                    if p_val == f_val:
                        continue
                        
                    all_dfmm_nodes_info[node_id] = (p_val, f_val)

        # --- 3. PEER_NODE_LIMIT のモードに応じてロジックを分岐 ---

        if limit_config == "half_p_group":
            # --- ロジック A: "half_p_group" (ご要望の動作) ---
            
            # P値でノードをグループ化
            p_groups = defaultdict(list)
            for node_id, (p_val, f_val) in all_dfmm_nodes_info.items():
                p_groups[p_val].append(node_id)

            for p_val, nodes_list in p_groups.items():
                if len(nodes_list) < 2:
                    continue
                
                # このグループの上限 = floor(ノード数 / 2)
                nodes_count = len(nodes_list)
                if nodes_count == 3:
                    # 3 の場合: ceil(3 / 2) = ceil(1.5) = 2
                    group_limit = math.ceil(nodes_count / 2)
                else:
                    # 2 の場合: floor(2 / 2) = 1
                    # 4 の場合: floor(4 / 2) = 2
                    # 5 の場合: floor(5 / 2) = 2
                    group_limit = math.floor(nodes_count / 2)
                
                print(f"  -> P-value group {p_val} (size {nodes_count}): Creating max {group_limit} peer(s).")
                
                nodes_generated_for_group = 0
                
                # このグループ内で 1:1 の組み合わせを作成
                for node_a_id, node_b_id in itertools.combinations(nodes_list, 2):
                    if nodes_generated_for_group >= group_limit:
                        break # このグループの上限に達した
                        
                    peer_nodes.append(
                        self._create_peer_node_entry(node_a_id, node_b_id, p_val)
                    )
                    nodes_generated_for_group += 1

        else:
            # --- ロジック B: "half_targets", 整数, "unlimited" (全体上限) ---
            
            all_nodes_list = list(all_dfmm_nodes_info.keys())
            
            # 全ノードの 1:1 の組み合わせをイテレート
            for node_a_id, node_b_id in itertools.combinations(all_nodes_list, 2):
                if len(peer_nodes) >= global_limit:
                    break # 全体の上限に達した

                p_val_a = all_dfmm_nodes_info[node_a_id][0]
                p_val_b = all_dfmm_nodes_info[node_b_id][0]

                # P値が一致するかチェック
                if p_val_a is None or p_val_a != p_val_b:
                    continue
                    
                peer_nodes.append(
                    self._create_peer_node_entry(node_a_id, node_b_id, p_val_a)
                )

        if len(peer_nodes) >= global_limit and global_limit != float('inf'):
            print(f"  -> Reached global peer node limit ({global_limit}). Stopped combination search early.")

        print(f"  -> Found {len(peer_nodes)} potential peer-mixing combinations.")
        return peer_nodes

    def _create_peer_node_entry(self, node_a_id, node_b_id, p_val):
        """ヘルパー: ピア(R)ノードの辞書エントリを作成する"""
        (m_a, l_a, k_a) = node_a_id
        (m_b, l_b, k_b) = node_b_id
        
        # ソートして名前を一定にする ( (A,B) と (B,A) が同じ名前になるように )
        if (m_a, l_a, k_a) > (m_b, l_b, k_b):
            node_a_id, node_b_id = node_b_id, node_a_id
            (m_a, l_a, k_a) = node_a_id
            (m_b, l_b, k_b) = node_b_id

        name = f"peer_mixer_t{m_a}l{l_a}k{k_a}-t{m_b}l{l_b}k{k_b}"
        return {
            "name": name,
            "source_a_id": node_a_id,
            "source_b_id": node_b_id,
            "p_value": p_val,
        }

    def _precompute_potential_sources_v2(self):
        source_map = {}
        all_dest_nodes = [
            (target_idx, level, node_idx)
            for target_idx, tree in enumerate(self.forest)
            for level, nodes in tree.items()
            for node_idx in range(len(nodes))
        ]
        all_dfmm_sources = list(all_dest_nodes)
        all_peer_sources = [("R", i, 0) for i in range(len(self.peer_nodes))]
        all_sources = all_dfmm_sources + all_peer_sources

        for (
            (dst_target_idx, dst_level, dst_node_idx),
            (src_target_idx, src_level, src_node_idx),
        ) in itertools.product(all_dest_nodes, all_sources):
            p_dst = self.p_value_maps[dst_target_idx][(dst_level, dst_node_idx)]
            f_dst = self.targets_config[dst_target_idx]["factors"][dst_level]

            if src_target_idx == "R":
                peer_node = self.peer_nodes[src_level]
                p_src = peer_node["p_value"]
                l_src_eff = max(
                    peer_node["source_a_id"][1], peer_node["source_b_id"][1]
                )
                is_valid_level_connection = (l_src_eff > dst_level)
            else:
                p_src = self.p_value_maps[src_target_idx][(src_level, src_node_idx)]
                l_src_eff = src_level
                if (dst_target_idx, dst_level, dst_node_idx) == (
                    src_target_idx,
                    src_level,
                    src_node_idx,
                ):
                    continue

                # 1. 供給元が中間ノード (level > 0) の場合
                is_intermediate_node_connection = (l_src_eff > dst_level)
                
                # 2. 供給元が最終ノード (level == 0) の場合
                #    Config フラグが True の場合のみ許可
                is_final_node_connection = (
                    (l_src_eff == 0) and Config.ENABLE_FINAL_PRODUCT_SHARING
                )
                
                # どちらかがTrueであれば有効
                is_valid_level_connection = (
                    is_intermediate_node_connection or is_final_node_connection
                )
            if not is_valid_level_connection:
                continue
            if Config.MAX_LEVEL_DIFF is not None and l_src_eff > dst_level + Config.MAX_LEVEL_DIFF:
                continue
            if (p_dst // f_dst) % p_src != 0:
                continue

            key = (dst_target_idx, dst_level, dst_node_idx)
            if key not in source_map:
                source_map[key] = []
            source_map[key].append((src_target_idx, src_level, src_node_idx))
        return source_map

    def _create_sharing_vars_for_node(self, dst_target_idx, dst_level, dst_node_idx):
        """
        共有液量を表す変数の「キー」の辞書を作成します。
        値は OrToolsSolver が設定するため、ここではプレースホルダー (None) すら不要です。
        """
        potential_sources = self.potential_sources_map.get(
            (dst_target_idx, dst_level, dst_node_idx), []
        )
        intra_vars, inter_vars = {}, {}

        for src_target_idx, src_level, src_node_idx in potential_sources:
            if src_target_idx == dst_target_idx:
                # (ツリー内)
                key_str = create_intra_key(src_level, src_node_idx)
                key = f"from_{key_str}"
                intra_vars[key] = None 
            else:
                if src_target_idx == "R":
                    # (ピア R)
                    key_str = create_peer_key(src_level)
                    key = f"from_{key_str}"
                    inter_vars[key] = None 
                else:
                    # (ツリー間)
                    key_str = create_inter_key(src_target_idx, src_level, src_node_idx)
                    key = f"from_{key_str}"
                    inter_vars[key] = None 
        return intra_vars, inter_vars

    def _define_sharing_variables(self):
        for dst_target_idx, tree_dst in enumerate(self.forest):
            for dst_level, nodes_dst in tree_dst.items():
                for dst_node_idx, node in enumerate(nodes_dst):
                    intra, inter = self._create_sharing_vars_for_node(
                        dst_target_idx, dst_level, dst_node_idx
                    )
                    # node (空の辞書) にキーを追加
                    node["intra_sharing_vars"] = intra
                    node["inter_sharing_vars"] = inter

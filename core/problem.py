import itertools
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
        print("Defining potential peer-mixing nodes (1:1 mix)...")
        peer_nodes = []

        all_dfmm_nodes = []
        for target_idx, tree in enumerate(self.forest):
            for level, nodes in tree.items():
                for node_idx, node in enumerate(nodes):
                    if level == 0:
                        continue
                    # 'node' は空の辞書ですが、存在チェック(combinations)のためタプルに入れます
                    all_dfmm_nodes.append(((target_idx, level, node_idx), node))

        for (node_a_id, node_a), (node_b_id, node_b) in itertools.combinations(
            all_dfmm_nodes, 2
        ):
            m_a, l_a, k_a = node_a_id
            m_b, l_b, k_b = node_b_id

            p_val_a = self.p_value_maps[m_a].get((l_a, k_a))
            p_val_b = self.p_value_maps[m_b].get((l_b, k_b))

            if p_val_a is None or p_val_a != p_val_b:
                continue

            f_a = self.targets_config[m_a]["factors"][l_a]
            f_b = self.targets_config[m_b]["factors"][l_b]
            is_leaf_a = p_val_a == f_a
            is_leaf_b = p_val_b == f_b
            if is_leaf_a and is_leaf_b:
                continue

            name = f"peer_mixer_t{m_a}l{l_a}k{k_a}-t{m_b}l{l_b}k{k_b}"

            peer_node = {
                "name": name,
                "source_a_id": node_a_id,
                "source_b_id": node_b_id,
                "p_value": p_val_a,
                # ★ プレースホルダーだった "ratio_vars" と "input_vars" を削除
            }
            peer_nodes.append(peer_node)

        print(f"  -> Found {len(peer_nodes)} potential peer-mixing combinations.")
        return peer_nodes

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
                intra_vars[key] = None # ★ OrToolsSolver がキーのみ参照するため None を設定
            else:
                if src_target_idx == "R":
                    # (ピア R)
                    key_str = create_peer_key(src_level)
                    key = f"from_{key_str}"
                    inter_vars[key] = None # ★
                else:
                    # (ツリー間)
                    key_str = create_inter_key(src_target_idx, src_level, src_node_idx)
                    key = f"from_{key_str}"
                    inter_vars[key] = None # ★
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

# core/model/problem.py
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
    """
    最適化問題の構造を定義するクラス。
    DFMMで計算されたツリー構造に基づき、ノード変数、共有可能性、
    ピア(R)ノードの定義などを行います。
    """

    def __init__(self, targets_config, tree_structures, p_value_maps):
        self.targets_config = targets_config
        self.num_reagents = len(targets_config[0]["ratios"]) if targets_config else 0
        self.tree_structures = tree_structures
        self.p_value_maps = p_value_maps
        
        # 1. 基本的なDFMMノードの骨格を定義
        self.forest = self._define_base_variables()
        
        # 2. ピア(R)ノード（1:1混合）の候補を定義
        self.peer_nodes = self._define_peer_mixing_nodes()
        
        # 3. 共有可能な接続（Potential Sources）を事前計算
        self.potential_sources_map = self._precompute_potential_sources_v2()
        
        # 4. 各ノードに共有変数のプレースホルダーを追加
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
                    # 空の辞書を追加。後に共有変数が格納されます。
                    level_nodes.append({})

                tree_data[level] = level_nodes
            forest_data.append(tree_data)
        return forest_data

    # --- [Refactored] ピア(R)ノード生成関連メソッド ---

    def _define_peer_mixing_nodes(self):
        """
        P値が一致する中間ノードのペア(1:1混合)を定義します。
        リファクタリングにより、設定解釈・収集・生成のフェーズに分割しました。
        """
        print("Defining potential peer-mixing nodes...")
        peer_nodes = []
        
        # 1. 設定の解釈 (モードと上限値の決定)
        mode, global_limit = self._resolve_peer_limit_config()

        # 2. 候補ノード情報の収集 (P値ごとにグループ化)
        nodes_by_p_value = self._collect_dfmm_nodes_by_p_value()
        
        # 3. ピアの生成
        if mode == "half_p_group":
            # モードA: P値グループごとに上限を設けて生成
            for p_val, nodes_list in nodes_by_p_value.items():
                if len(nodes_list) < 2:
                    continue
                
                # グループごとの上限 = floor(ノード数 / 2)
                # (例: 3ノードなら ceil(1.5)=2 にする等、微調整が可能)
                group_limit = math.floor(len(nodes_list) / 2)
                if len(nodes_list) == 3:
                    group_limit = 2 

                print(f"  -> P-value group {p_val} (size {len(nodes_list)}): Creating max {group_limit} peer(s).")
                self._generate_peers_from_list(nodes_list, p_val, group_limit, peer_nodes)
        else:
            # モードB: 全体リストから上限まで生成
            all_nodes_flat = [n for sublist in nodes_by_p_value.values() for n in sublist]
            self._generate_peers_from_list(all_nodes_flat, None, global_limit, peer_nodes)

        if len(peer_nodes) >= global_limit and global_limit != float('inf'):
            print(f"  -> Reached global peer node limit ({global_limit}). Stopped combination search early.")

        print(f"  -> Found {len(peer_nodes)} potential peer-mixing combinations.")
        return peer_nodes

    def _resolve_peer_limit_config(self):
        """Configから制限モードと全体上限値を解決します"""
        limit_config = getattr(Config, "PEER_NODE_LIMIT", "half_targets")
        
        if limit_config == "half_p_group":
            print("  -> Mode: 'half_p_group'. Limiting peers per P-value group.")
            return "half_p_group", float('inf')
            
        num_targets = len(self.targets_config)
        global_limit = float('inf')
        
        if isinstance(limit_config, int):
            global_limit = limit_config
        elif limit_config == "half_targets":
            global_limit = math.floor(num_targets / 2) if num_targets > 0 else 0
            
        print(f"  -> Mode: Global Limit. Config='{limit_config}' (Resolved Global Limit: {global_limit})")
        return "global", global_limit

    def _collect_dfmm_nodes_by_p_value(self):
        """DFMMノードをP値ごとにグループ化して返します"""
        p_groups = defaultdict(list)
        for target_idx, tree in enumerate(self.forest):
            for level, nodes in tree.items():
                if level == 0: continue # ルートノードは除外
                for node_idx, _ in enumerate(nodes):
                    p_val = self.p_value_maps[target_idx].get((level, node_idx))
                    f_val = self.targets_config[target_idx]["factors"][level]
                    
                    # リーフノード (P == F) は除外
                    if p_val is not None and p_val != f_val: 
                        node_id = (target_idx, level, node_idx)
                        p_groups[p_val].append(node_id)
        return p_groups

    def _generate_peers_from_list(self, nodes_list, p_val_force, limit, out_peer_nodes):
        """
        ノードリストから2つの組み合わせを作成し、条件を満たすものを out_peer_nodes に追加します。
        
        Args:
            nodes_list (list): 組み合わせ候補のノードIDリスト
            p_val_force (int or None): 強制するP値。Noneの場合はマップから参照して一致確認を行う。
            limit (int): 生成上限数
            out_peer_nodes (list): 結果格納用リスト
        """
        count = 0
        # itertools.combinations で重複なしのペアを生成
        for node_a, node_b in itertools.combinations(nodes_list, 2):
            if count >= limit:
                break
            
            p_val = p_val_force
            
            # P値が未指定(globalモード)の場合、ここで一致確認を行う
            if p_val is None:
                m_a, l_a, k_a = node_a
                m_b, l_b, k_b = node_b
                p_a = self.p_value_maps[m_a].get((l_a, k_a))
                p_b = self.p_value_maps[m_b].get((l_b, k_b))
                
                if p_a is None or p_a != p_b:
                    continue # P値が一致しないペアはスキップ
                p_val = p_a

            out_peer_nodes.append(self._create_peer_node_entry(node_a, node_b, p_val))
            count += 1

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

    # --- 共有（Sharing）関連メソッド ---

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
                is_final_node_connection = (
                    (l_src_eff == 0) and Config.ENABLE_FINAL_PRODUCT_SHARING
                )
                
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
        """各ノードの辞書に共有変数のプレースホルダーを追加します"""
        for dst_target_idx, tree_dst in enumerate(self.forest):
            for dst_level, nodes_dst in tree_dst.items():
                for dst_node_idx, node in enumerate(nodes_dst):
                    intra, inter = self._create_sharing_vars_for_node(
                        dst_target_idx, dst_level, dst_node_idx
                    )
                    # node (空の辞書) にキーを追加
                    node["intra_sharing_vars"] = intra
                    node["inter_sharing_vars"] = inter
import time
import sys
from collections import defaultdict
from ortools.sat.python import cp_model
from utils.config_loader import Config
from utils import (
    create_dfmm_node_name,
    create_intra_key,
    create_inter_key,
    create_peer_key,
    parse_sharing_key,
)
from .solution import OrToolsSolutionModel

sys.setrecursionlimit(2000)

class OrToolsSolver:
    """MTWMProblem を Or-Tools CP-SAT モデルに変換し、最適化を実行するクラス。"""

    def __init__(self, problem, objective_mode="waste"):
        self.problem = problem
        self.objective_mode = objective_mode
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()
        
        # --- Config設定の適用 ---
        if Config.MAX_CPU_WORKERS and Config.MAX_CPU_WORKERS > 0:
            self.solver.parameters.num_workers = Config.MAX_CPU_WORKERS
        
        if Config.MAX_TIME_PER_RUN_SECONDS and Config.MAX_TIME_PER_RUN_SECONDS > 0:
            self.solver.parameters.max_time_in_seconds = float(Config.MAX_TIME_PER_RUN_SECONDS)

        if Config.ABSOLUTE_GAP_LIMIT and Config.ABSOLUTE_GAP_LIMIT > 0:
            self.solver.parameters.absolute_gap_limit = float(Config.ABSOLUTE_GAP_LIMIT)
        
        self.solver.parameters.log_search_progress = True
        self.solver.parameters.linearization_level = 2
            
        self.forest_vars = []
        self.peer_vars = []
        
        # モデル構築
        self._set_variables_and_constraints()

    def solve(self):
        start_time = time.time()
        print(f"\n--- Solving (mode: {self.objective_mode.upper()}) with Or-Tools ---")
        
        status = self.solver.Solve(self.model)
        
        elapsed_time = time.time() - start_time
        best_model = None
        best_value = None
        best_analysis = None

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            best_value = self.solver.ObjectiveValue()
            print(f"Or-Tools found solution with {self.objective_mode}: {int(best_value)}")
            
            best_model = OrToolsSolutionModel(
                self.problem, self.solver, self.forest_vars, self.peer_vars
            )
            best_analysis = best_model.analyze()
        else:
            print(f"Or-Tools Solver status: {self.solver.StatusName(status)}")
                
        print("--- Or-Tools Solver Finished ---")
        return best_model, best_value, best_analysis, elapsed_time
    
    def _set_variables_and_constraints(self):
        """
        モデル構築のメインフローを制御するメソッド。
        """
        self._define_or_tools_variables()
        self._set_initial_constraints()
        self._set_conservation_constraints()
        self._set_concentration_constraints()
        self._set_ratio_sum_constraints()
        self._set_leaf_node_constraints()
        self._set_mixer_capacity_constraints()
        self._set_activity_constraints()
        self._set_peer_mixing_constraints()
        self._set_symmetry_breaking_constraints()
        self._set_input_degree_constraints()
        self.objective_variable = self._set_objective_function()
        self._set_max_reagent_input_per_node_constraint()

    def _define_or_tools_variables(self):
        """
        変数を定義し、self.forest_vars と self.peer_vars に格納します。
        """
            
        # 1. DFMMノード変数の定義 (変更なし)
        for target_idx, z3_tree in enumerate(self.problem.forest):
            tree_data = {}
            for level, z3_nodes in z3_tree.items():
                level_nodes = []
                for node_idx, z3_node in enumerate(z3_nodes):
                    node_name = create_dfmm_node_name(target_idx, level, node_idx)
                    
                    p_node = self.problem.p_value_maps[target_idx][(level, node_idx)]
                    f_value = self.problem.targets_config[target_idx]["factors"][level]
                    reagent_max = max(0, f_value - 1)
                    
                    node_vars = {
                        "ratio_vars": [
                            self.model.NewIntVar(
                                0, p_node, f"ratio_{node_name}_r{t}"
                            )
                            for t in range(self.problem.num_reagents)
                        ],
                        "reagent_vars": [
                            self.model.NewIntVar(
                                0, reagent_max, f"reagent_vol_{node_name}_r{t}"
                            )
                            for t in range(self.problem.num_reagents)
                        ],
                        "intra_sharing_vars": {},
                        "inter_sharing_vars": {},
                        "total_input_var": self.model.NewIntVar(
                            0, f_value, f"TotalInput_{node_name}"
                        ),
                        "is_active_var": self.model.NewBoolVar(f"IsActive_{node_name}"),
                        "waste_var": self.model.NewIntVar(
                            0, f_value, f"waste_{node_name}"
                        ),
                    }
                    
                    max_sharing_vol = min(f_value, Config.MAX_SHARING_VOLUME or f_value)
                    
                    for key in z3_node.get("intra_sharing_vars", {}).keys():
                        share_name = (
                            f"share_intra_t{target_idx}_l{level}_k{node_idx}_{key}"
                        )
                        node_vars["intra_sharing_vars"][key] = self.model.NewIntVar(
                            0, max_sharing_vol, share_name
                        )
                    for key in z3_node.get("inter_sharing_vars", {}).keys():
                        share_name = (
                            f"share_inter_t{target_idx}_l{level}_k{node_idx}_{key}"
                        )
                        node_vars["inter_sharing_vars"][key] = self.model.NewIntVar(
                            0, max_sharing_vol, share_name
                        )
                    level_nodes.append(node_vars)
                tree_data[level] = level_nodes
            self.forest_vars.append(tree_data)
            
        # 2. ピア(R)ノード変数の定義 [Modified]
        for i, z3_peer_node in enumerate(self.problem.peer_nodes):
            name = z3_peer_node["name"]
            p_val = z3_peer_node["p_value"]
            is_generic = z3_peer_node.get("is_generic", False)

            node_vars = {
                "name": name,
                "p_value": p_val,
                "is_generic": is_generic, # フラグ保持
                "ratio_vars": [
                    self.model.NewIntVar(0, p_val, f"ratio_{name}_r{t}")
                    for t in range(self.problem.num_reagents)
                ],
                "total_input_var": self.model.NewIntVar(0, 2, f"TotalInput_{name}"),
                "is_active_var": self.model.NewBoolVar(f"IsActive_{name}"),
                "waste_var": self.model.NewIntVar(0, 2, f"waste_{name}"),
            }

            if is_generic:
                # --- [新ロジック] 動的選択用の変数 ---
                candidates = z3_peer_node["candidate_sources"]
                input_selection_vars = {}
                for src_id in candidates:
                    var_name = f"select_{name}_from_t{src_id[0]}l{src_id[1]}k{src_id[2]}"
                    input_selection_vars[src_id] = self.model.NewBoolVar(var_name)
                
                node_vars["input_vars"] = input_selection_vars
                node_vars["candidate_sources"] = candidates
            else:
                # --- [旧ロジック] 固定ペア用の変数 ---
                node_vars["source_a_id"] = z3_peer_node["source_a_id"]
                node_vars["source_b_id"] = z3_peer_node["source_b_id"]
                node_vars["input_vars"] = {
                    "from_a": self.model.NewIntVar(0, 1, f"share_peer_a_to_{name}"),
                    "from_b": self.model.NewIntVar(0, 1, f"share_peer_b_to_{name}"),
                }

            self.peer_vars.append(node_vars)

            
    # --- ヘルパーメソッド ---

    def _get_input_vars(self, node_vars):
        return (
            node_vars.get("reagent_vars", [])
            + list(node_vars.get("intra_sharing_vars", {}).values())
            + list(node_vars.get("inter_sharing_vars", {}).values())
        )

    def _get_outgoing_vars(self, src_target_idx, src_level, src_node_idx):
        outgoing = []
        key_intra = f"from_{create_intra_key(src_level, src_node_idx)}"
        key_inter = f"from_{create_inter_key(src_target_idx, src_level, src_node_idx)}"
        
        # 1. DFMMノードへの供給チェック (変更なし)
        for dst_target_idx, tree_dst in enumerate(self.forest_vars):
            for dst_level, level_dst in tree_dst.items():
                for dst_node_idx, node_dst in enumerate(level_dst):
                    if src_target_idx == dst_target_idx and key_intra in node_dst.get(
                        "intra_sharing_vars", {}
                    ):
                        outgoing.append(node_dst["intra_sharing_vars"][key_intra])
                    elif src_target_idx != dst_target_idx and key_inter in node_dst.get(
                        "inter_sharing_vars", {}
                    ):
                        outgoing.append(node_dst["inter_sharing_vars"][key_inter])
        
        # 2. ピア(R)ノードへの供給チェック [Modified]
        src_id = (src_target_idx, src_level, src_node_idx)
        
        for or_peer_node in self.peer_vars:
            input_vars = or_peer_node["input_vars"]
            
            if or_peer_node.get("is_generic"):
                # [Dynamic] 候補リストに含まれていれば、その選択変数を返す
                if src_id in input_vars:
                    outgoing.append(input_vars[src_id])
            else:
                # [Fixed] IDが一致すれば、固定の入力変数を返す
                if src_id == or_peer_node["source_a_id"]:
                    outgoing.append(input_vars["from_a"])
                if src_id == or_peer_node["source_b_id"]:
                    outgoing.append(input_vars["from_b"])
                    
        return outgoing

    def _get_outgoing_vars_from_peer(self, peer_node_index):
        outgoing = []
        key_inter = f"from_{create_peer_key(peer_node_index)}"
        for dst_target_idx, tree_dst in enumerate(self.forest_vars):
            for dst_level, level_dst in tree_dst.items():
                for dst_node_idx, node_dst in enumerate(level_dst):
                    if key_inter in node_dst.get("inter_sharing_vars", {}):
                        outgoing.append(node_dst["inter_sharing_vars"][key_inter])
        return outgoing

    def _iterate_all_nodes(self):
        for target_idx, tree in enumerate(self.forest_vars):
            for level, nodes in tree.items():
                for node_idx, node in enumerate(nodes):
                    yield target_idx, level, node_idx, node

    # --- 制約 (Constraints) 設定メソッド ---

    def _set_initial_constraints(self):
        """[制約1] 最終ターゲット(root, level 0)の比率"""
        for target_idx, target in enumerate(self.problem.targets_config):
            root_vars = self.forest_vars[target_idx][0][0]
            for reagent_idx in range(self.problem.num_reagents):
                self.model.Add(
                    root_vars["ratio_vars"][reagent_idx]
                    == target["ratios"][reagent_idx]
                )

    def _set_conservation_constraints(self):
        """[制約2] 流量保存則"""
        for m_src, l_src, k_src, node_vars in self._iterate_all_nodes():
            total_produced = node_vars["total_input_var"]
            self.model.Add(total_produced == sum(self._get_input_vars(node_vars)))

    def _set_concentration_constraints(self):
        """[制約3] 濃度保存則"""
        for dst_target_idx, dst_level, dst_node_idx, node_vars in self._iterate_all_nodes():
            p_dst = self.problem.p_value_maps[dst_target_idx][(dst_level, dst_node_idx)]
            f_dst = self.problem.targets_config[dst_target_idx]["factors"][dst_level]
            node_name_prefix = f"t{dst_target_idx}l{dst_level}k{dst_node_idx}"

            for reagent_idx in range(self.problem.num_reagents):
                lhs = f_dst * node_vars["ratio_vars"][reagent_idx]
                rhs_terms = []
                rhs_terms.append(self._add_concentration_term_for_reagents(node_vars, p_dst, reagent_idx))
                rhs_terms.extend(self._add_concentration_term_for_intra_sharing(node_vars, p_dst, reagent_idx, dst_target_idx, node_name_prefix))
                rhs_terms.extend(self._add_concentration_term_for_inter_sharing(node_vars, p_dst, reagent_idx, node_name_prefix))
                self.model.Add(lhs == sum(rhs_terms))

    def _add_concentration_term_for_reagents(self, node_vars, p_dst, reagent_idx):
        return p_dst * node_vars["reagent_vars"][reagent_idx]

    def _add_concentration_term_for_intra_sharing(self, node_vars, p_dst, reagent_idx, dst_target_idx, node_name_prefix):
        rhs_terms = []
        for key, w_var in node_vars.get("intra_sharing_vars", {}).items():
            key_no_prefix = key.replace("from_", "")
            parsed_key = parse_sharing_key(key_no_prefix)
            l_src = parsed_key["level"]
            k_src = parsed_key["node_idx"]
            r_src = self.forest_vars[dst_target_idx][l_src][k_src]["ratio_vars"][reagent_idx]
            p_src = self.problem.p_value_maps[dst_target_idx][(l_src, k_src)]
            
            f_src = self.problem.targets_config[dst_target_idx]["factors"][l_src]
            max_w = f_src
            if Config.MAX_SHARING_VOLUME is not None:
                max_w = min(f_src, Config.MAX_SHARING_VOLUME)

            current_product_bound = p_src * max_w

            prod_name = f"Prod_intra_{node_name_prefix}_r{reagent_idx}_from_{key}"
            product_var = self.model.NewIntVar(0, current_product_bound, prod_name)
            self.model.AddMultiplicationEquality(product_var, [r_src, w_var])
            
            rhs_terms.append(product_var * (p_dst // p_src))
        return rhs_terms

    def _add_concentration_term_for_inter_sharing(self, node_vars, p_dst, reagent_idx, node_name_prefix):
        rhs_terms = []
        for key, w_var in node_vars.get("inter_sharing_vars", {}).items():
            key_no_prefix = key.replace("from_", "")
            parsed_key = parse_sharing_key(key_no_prefix)
            
            if parsed_key["type"] == "PEER":
                r_node_idx = parsed_key["idx"]
                or_peer_node = self.peer_vars[r_node_idx]
                r_src = or_peer_node["ratio_vars"][reagent_idx]
                p_src = or_peer_node["p_value"]
                max_w = 2 
            else:
                m_src = parsed_key["target_idx"]
                l_src = parsed_key["level"]
                k_src = parsed_key["node_idx"]
                r_src = self.forest_vars[m_src][l_src][k_src]["ratio_vars"][reagent_idx]
                p_src = self.problem.p_value_maps[m_src][(l_src, k_src)]
                f_src = self.problem.targets_config[m_src]["factors"][l_src]
                max_w = f_src
                if Config.MAX_SHARING_VOLUME is not None:
                    max_w = min(f_src, Config.MAX_SHARING_VOLUME)
            
            current_product_bound = p_src * max_w
            
            prod_name = f"Prod_inter_{node_name_prefix}_r{reagent_idx}_from_{key}"
            product_var = self.model.NewIntVar(0, current_product_bound, prod_name)
            self.model.AddMultiplicationEquality(product_var, [r_src, w_var])
            rhs_terms.append(product_var * (p_dst // p_src))
        return rhs_terms
    
    def _set_ratio_sum_constraints(self):
        """[制約4] 各ノードの比率の合計値"""
        for target_idx, level, node_idx, node_vars in self._iterate_all_nodes():
            p_node = self.problem.p_value_maps[target_idx][(level, node_idx)]
            is_active = node_vars["is_active_var"]
            
            self.model.Add(sum(node_vars["ratio_vars"]) == p_node).OnlyEnforceIf(is_active)
            for r_var in node_vars["ratio_vars"]:
                self.model.Add(r_var == 0).OnlyEnforceIf(is_active.Not())

    def _set_leaf_node_constraints(self):
        """[制約5] リーフノードの制約"""
        for target_idx, level, node_idx, node_vars in self._iterate_all_nodes():
            p_node = self.problem.p_value_maps[target_idx][(level, node_idx)]
            f_node = self.problem.targets_config[target_idx]["factors"][level]
            if p_node == f_node:
                for reagent_idx in range(self.problem.num_reagents):
                    self.model.Add(
                        node_vars["ratio_vars"][reagent_idx]
                        == node_vars["reagent_vars"][reagent_idx]
                    )

    def _set_mixer_capacity_constraints(self):
        """[制約6] ミキサー容量の制約"""
        for target_idx, level, node_idx, node_vars in self._iterate_all_nodes():
            f_value = self.problem.targets_config[target_idx]["factors"][level]
            total_sum = node_vars["total_input_var"]
            is_active = node_vars["is_active_var"]
            
            if level == 0:
                self.model.Add(total_sum == f_value)
            else:
                self.model.Add(total_sum == is_active * f_value)

    def _set_activity_constraints(self):
        """[制約8] ノードのアクティビティ制約"""
        # (A) DFMMノード
        for (src_target_idx, src_level, src_node_idx, node_vars) in self._iterate_all_nodes():
            if src_level == 0: continue
            total_used = sum(self._get_outgoing_vars(src_target_idx, src_level, src_node_idx))
            is_active = node_vars["is_active_var"]
            
            self.model.Add(total_used >= 1).OnlyEnforceIf(is_active)
            self.model.Add(total_used == 0).OnlyEnforceIf(is_active.Not())
            
        # (B) ピア(R)ノード
        for i, or_peer_node in enumerate(self.peer_vars):
            total_used = sum(self._get_outgoing_vars_from_peer(i))
            is_active = or_peer_node["is_active_var"]

            self.model.Add(total_used >= 1).OnlyEnforceIf(is_active)
            self.model.Add(total_used == 0).OnlyEnforceIf(is_active.Not())

    def _set_peer_mixing_constraints(self):
        """[制約9] ピア(R)ノードの混合制約 (分岐対応版) [Modified]"""
        for i, or_peer_node in enumerate(self.peer_vars):
            if or_peer_node.get("is_generic"):
                self._set_dynamic_peer_constraints(or_peer_node)
            else:
                self._set_fixed_peer_constraints(or_peer_node)

    def _set_dynamic_peer_constraints(self, or_peer_node):
        """新ロジック用の制約: 候補リストから2つ選ぶ"""
        total_input = or_peer_node["total_input_var"]
        is_active = or_peer_node["is_active_var"]
        input_vars_dict = or_peer_node["input_vars"]
        p_val = or_peer_node["p_value"]
        
        # 1. 選択数制約 (Activeなら2つ選ぶ)
        selection_sum = sum(input_vars_dict.values())
        self.model.Add(selection_sum == 2).OnlyEnforceIf(is_active)
        self.model.Add(selection_sum == 0).OnlyEnforceIf(is_active.Not())
        
        # TotalInputは2
        self.model.Add(total_input == 2).OnlyEnforceIf(is_active)
        self.model.Add(total_input == 0).OnlyEnforceIf(is_active.Not())
        
        # 2. 比率計算 (条件付き加算)
        r_new_vars = or_peer_node["ratio_vars"]
        self.model.Add(sum(r_new_vars) == p_val).OnlyEnforceIf(is_active) # 合計整合性
        self.model.Add(sum(r_new_vars) == 0).OnlyEnforceIf(is_active.Not())

        for reagent_idx in range(self.problem.num_reagents):
            lhs = 2 * r_new_vars[reagent_idx]
            rhs_terms = []
            
            for src_id, select_var in input_vars_dict.items():
                m, l, k = src_id
                src_ratio_var = self.forest_vars[m][l][k]["ratio_vars"][reagent_idx]
                
                # intermediate = src_ratio if selected else 0
                term = self.model.NewIntVar(0, p_val, f"term_{or_peer_node['name']}_r{reagent_idx}_{m}_{l}_{k}")
                self.model.Add(term == src_ratio_var).OnlyEnforceIf(select_var)
                self.model.Add(term == 0).OnlyEnforceIf(select_var.Not())
                rhs_terms.append(term)
            
            self.model.Add(lhs == sum(rhs_terms)).OnlyEnforceIf(is_active)

    def _set_fixed_peer_constraints(self, or_peer_node):
        """旧ロジック用の制約: 固定ペアから入力"""
        total_input = or_peer_node["total_input_var"]
        is_active = or_peer_node["is_active_var"]
        w_a = or_peer_node["input_vars"]["from_a"] 
        w_b = or_peer_node["input_vars"]["from_b"] 

        self.model.Add(total_input == w_a + w_b)

        self.model.Add(w_a == 1).OnlyEnforceIf(is_active)
        self.model.Add(w_b == 1).OnlyEnforceIf(is_active)

        self.model.Add(total_input == 0).OnlyEnforceIf(is_active.Not())
        self.model.Add(w_a == 0).OnlyEnforceIf(is_active.Not())
        self.model.Add(w_b == 0).OnlyEnforceIf(is_active.Not())

        p_val = or_peer_node["p_value"]
        r_new_vars = or_peer_node["ratio_vars"]
        self.model.Add(sum(r_new_vars) == p_val).OnlyEnforceIf(is_active)
        self.model.Add(sum(r_new_vars) == 0).OnlyEnforceIf(is_active.Not())
        
        m_a, l_a, k_a = or_peer_node["source_a_id"]
        r_a_vars = self.forest_vars[m_a][l_a][k_a]["ratio_vars"]
        m_b, l_b, k_b = or_peer_node["source_b_id"]
        r_b_vars = self.forest_vars[m_b][l_b][k_b]["ratio_vars"]
        
        for reagent_idx in range(self.problem.num_reagents):
            lhs = 2 * r_new_vars[reagent_idx]
            rhs = r_a_vars[reagent_idx] + r_b_vars[reagent_idx]
            self.model.Add(lhs == rhs).OnlyEnforceIf(is_active)
    
    def _set_input_degree_constraints(self):
        """[追加] 入力次数(Fan-in)の制限"""
        max_fan_in = getattr(Config, "MAX_SHARED_INPUTS", None)

        if max_fan_in is None:
            return

        print(f"--- Setting max shared input types (Fan-in) per node to {max_fan_in} ---")

        for target_idx, level, node_idx, node_vars in self._iterate_all_nodes():
            sharing_vars = []
            sharing_vars.extend(node_vars.get("intra_sharing_vars", {}).values())
            sharing_vars.extend(node_vars.get("inter_sharing_vars", {}).values())
            
            if not sharing_vars:
                continue

            is_used_bools = []
            for var in sharing_vars:
                is_used = self.model.NewBoolVar(f"is_used_input_{var.Name()}")
                self.model.Add(var > 0).OnlyEnforceIf(is_used)
                self.model.Add(var == 0).OnlyEnforceIf(is_used.Not())
                is_used_bools.append(is_used)
            
            self.model.Add(sum(is_used_bools) <= max_fan_in)

    def _set_symmetry_breaking_constraints(self):
        """対称性排除制約: 探索空間を削減するために等価な解を排除する"""
        
        # 1. DFMMノード間の対称性排除 (既存)
        # 同じレベルのノード同士で、左側のノードが優先的に使われるようにする
        for m, tree_vars in enumerate(self.forest_vars):
            for l, nodes_vars_list in tree_vars.items():
                if len(nodes_vars_list) > 1:
                    for k in range(len(nodes_vars_list) - 1):
                        node_k = nodes_vars_list[k]
                        node_k1 = nodes_vars_list[k+1]
                        
                        # k が非アクティブなら k+1 も非アクティブ
                        self.model.Add(node_k["is_active_var"] >= node_k1["is_active_var"])
                        # k の処理量が k+1 以上
                        self.model.Add(node_k["total_input_var"] >= node_k1["total_input_var"])

        # 2. Generic Peer Node (動的ペアノード) 間の対称性排除
        # 同じP値を持つペアノードのグループ内で、インデックスが小さい順に使われるように強制する
        peers_by_p = defaultdict(list)
        for p_var in self.peer_vars:
            if p_var.get("is_generic"):
                peers_by_p[p_var["p_value"]].append(p_var)
        
        for p_val, peers in peers_by_p.items():
            # 同じP値のペアノードが複数ある場合
            if len(peers) > 1:
                print(f"--- Adding symmetry breaking for {len(peers)} generic peers (P={p_val}) ---")
                for i in range(len(peers) - 1):
                    peer_k = peers[i]
                    peer_k1 = peers[i+1]
                    
                    # 1つ目が使われないなら、2つ目も使わない
                    self.model.Add(peer_k["is_active_var"] >= peer_k1["is_active_var"])

    def _set_max_reagent_input_per_node_constraint(self):
        """[制約11] 試薬投入量上限をソフト制約として設定"""
        max_limit = Config.MAX_TOTAL_REAGENT_INPUT_PER_NODE

        if max_limit is None or max_limit <= 0:
            return

        print(
            f"--- Setting max total reagent input per node (Soft Constraint) to {max_limit} ---"
        )

        self.all_reagent_excess_vars = [] 

        for _, _, _, node_vars in self._iterate_all_nodes():
            reagent_vars = node_vars.get("reagent_vars", [])
            
            if reagent_vars:
                total_reagent_input = self.model.NewIntVar(0, 1000, "total_reagent_sum") 
                self.model.Add(total_reagent_input == sum(reagent_vars))
                
                excess_var = self.model.NewIntVar(0, 1000, "reagent_excess")
                self.model.Add(excess_var >= total_reagent_input - max_limit)
                
                self.all_reagent_excess_vars.append(excess_var)

    def _set_objective_function(self):
        """[制約10] 目的関数"""
        all_waste_vars = []
        all_activity_vars = []
        all_reagent_vars = []

        for (src_target_idx, src_level, src_node_idx, node_vars) in self._iterate_all_nodes():
            if src_level != 0:
                total_prod = node_vars["total_input_var"]
                total_used = sum(self._get_outgoing_vars(src_target_idx, src_level, src_node_idx))
                waste_var = node_vars["waste_var"]
                self.model.Add(waste_var == total_prod - total_used)
                all_waste_vars.append(waste_var)
            all_activity_vars.append(node_vars["is_active_var"])
            all_reagent_vars.extend(node_vars.get("reagent_vars", []))

        for i, or_peer_node in enumerate(self.peer_vars):
            total_prod = or_peer_node["total_input_var"]
            total_used = sum(self._get_outgoing_vars_from_peer(i))
            waste_var = or_peer_node["waste_var"]
            self.model.Add(waste_var == total_prod - total_used)
            all_waste_vars.append(waste_var)
            all_activity_vars.append(or_peer_node["is_active_var"])

        total_waste = sum(all_waste_vars)
        if self.objective_mode == "waste":
            self.model.Add(total_waste >= 1)
        total_operations = sum(all_activity_vars)
        total_reagents = sum(all_reagent_vars)

        penalty_weight = 100000 
        total_penalty = 0
        
        if hasattr(self, 'all_reagent_excess_vars') and self.all_reagent_excess_vars:
            total_penalty = sum(self.all_reagent_excess_vars) * penalty_weight

        if self.objective_mode == "waste":
            self.model.Minimize(total_waste + total_penalty)
            return total_waste
        elif self.objective_mode == "operations":
            self.model.Minimize(total_operations + total_penalty)
            return total_operations
        elif self.objective_mode == "reagents":
            self.model.Minimize(total_reagents + total_penalty)
            return total_reagents
        else:
            raise ValueError(f"Unknown optimization mode: '{self.objective_mode}'")

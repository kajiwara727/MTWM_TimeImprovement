import time
import sys
from collections import defaultdict
from typing import List, Dict, Any, Optional

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

class SolutionPrinter(cp_model.CpSolverSolutionCallback):
    """解が見つかるたびに進捗を表示するコールバッククラス"""
    def __init__(self):
        cp_model.CpSolverSolutionCallback.__init__(self)
        self.__solution_count = 0
        self.__start_time = time.time()

    def on_solution_callback(self):
        self.__solution_count += 1
        current_time = time.time()
        obj = self.ObjectiveValue()
        print(f"Solution #{self.__solution_count}: Objective = {obj}, Time = {current_time - self.__start_time:.2f}s")

    @property
    def solution_count(self):
        return self.__solution_count


class OrToolsSolver:
    """MTWMProblem を Or-Tools CP-SAT モデルに変換し、最適化を実行するクラス。"""

    def __init__(self, problem, objective_mode="waste"):
        self.problem = problem
        self.objective_mode = objective_mode
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()
        
        # 変数格納用コンテナ
        self.forest_vars = []
        self.peer_vars = []
        self.all_reagent_excess_vars = []
        
        # 初期化と設定
        self._configure_solver()
        self._set_variables_and_constraints()

    def _configure_solver(self):
        """ソルバーのパラメータ設定"""
        # --- 基本リソース設定 ---
        if Config.MAX_CPU_WORKERS and Config.MAX_CPU_WORKERS > 0:
            self.solver.parameters.num_workers = Config.MAX_CPU_WORKERS
        else:
            # デフォルトで全コア使用（0）または適度な並列数（8など）を推奨
            self.solver.parameters.num_workers = 0 
        
        if Config.MAX_TIME_PER_RUN_SECONDS and Config.MAX_TIME_PER_RUN_SECONDS > 0:
            self.solver.parameters.max_time_in_seconds = float(Config.MAX_TIME_PER_RUN_SECONDS)

        if Config.ABSOLUTE_GAP_LIMIT and Config.ABSOLUTE_GAP_LIMIT > 0:
            self.solver.parameters.absolute_gap_limit = float(Config.ABSOLUTE_GAP_LIMIT)
        
        # --- 探索アルゴリズムの強化 ---
        # 線形化レベル: 高くすると掛け算などの制約精度が上がるが計算コスト増
        self.solver.parameters.linearization_level = 2
        # コアベースの最適化を有効化
        self.solver.parameters.optimize_with_core = True 
        
        # カット（切除平面）の設定: 探索空間を削減する強力な機能
        self.solver.parameters.max_num_cuts = 2000 
        self.solver.parameters.cut_level = 2
        
        # 前処理とエンコーディング
        self.solver.parameters.boolean_encoding_level = 2
        self.solver.parameters.symmetry_level = 2 
        
        # ログ出力（コールバックと合わせて使用）
        self.solver.parameters.log_search_progress = True

    def solve(self):
        start_time = time.time()
        print(f"\n--- Solving (mode: {self.objective_mode.upper()}) with Or-Tools CP-SAT ---")
        
        # コールバックを使用して解を表示
        solution_printer = SolutionPrinter()
        status = self.solver.Solve(self.model, solution_printer)
        
        elapsed_time = time.time() - start_time
        best_model = None
        best_value = None
        best_analysis = None

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            best_value = self.solver.ObjectiveValue()
            status_str = "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE"
            print(f"Or-Tools finished: {status_str} solution found. Value: {int(best_value)}")
            print(f"Total solutions found: {solution_printer.solution_count}")
            
            best_model = OrToolsSolutionModel(
                self.problem, self.solver, self.forest_vars, self.peer_vars
            )
            best_analysis = best_model.analyze()
        else:
            print(f"Or-Tools Solver status: {self.solver.StatusName(status)}")
            # INFEASIBLEの場合、モデルの矛盾を調査するためのロジックをここに追加可能
                
        print("--- Or-Tools Solver Finished ---")
        return best_model, best_value, best_analysis, elapsed_time
    
    def _set_variables_and_constraints(self):
        """モデル構築のメインフロー"""
        self._define_or_tools_variables()
        self._set_initial_constraints()
        self._set_conservation_constraints()
        self._set_concentration_constraints()
        self._set_ratio_sum_constraints()
        self._set_leaf_node_constraints()
        self._set_mixer_capacity_constraints()
        
        # 対称性排除
        self._set_symmetry_breaking_constraints()
        
        self._set_activity_constraints()
        self._set_peer_mixing_constraints()
        self._set_input_degree_constraints()
        
        # 目的関数とソフト制約
        self._set_max_reagent_input_per_node_constraint()
        self._set_objective_function()
        
        # 探索戦略（ヒューリスティック）
        self._set_search_strategy()

    def _define_or_tools_variables(self):
        """変数定義：DFMMノードとPeerノードの変数を初期化"""
            
        # 1. DFMMノード変数の定義
        for target_idx, z3_tree in enumerate(self.problem.forest):
            tree_data = {}
            for level, z3_nodes in z3_tree.items():
                level_nodes = []
                for node_idx, z3_node in enumerate(z3_nodes):
                    node_name = create_dfmm_node_name(target_idx, level, node_idx)
                    
                    p_node = self.problem.p_value_maps[target_idx][(level, node_idx)]
                    f_value = self.problem.targets_config[target_idx]["factors"][level]
                    reagent_max = max(0, f_value - 1)
                    
                    # 変数辞書の作成
                    node_vars = {
                        "ratio_vars": [
                            self.model.NewIntVar(0, p_node, f"ratio_{node_name}_r{t}")
                            for t in range(self.problem.num_reagents)
                        ],
                        "reagent_vars": [
                            self.model.NewIntVar(0, reagent_max, f"reagent_vol_{node_name}_r{t}")
                            for t in range(self.problem.num_reagents)
                        ],
                        "intra_sharing_vars": {},
                        "inter_sharing_vars": {},
                        "total_input_var": self.model.NewIntVar(0, f_value, f"TotalInput_{node_name}"),
                        "is_active_var": self.model.NewBoolVar(f"IsActive_{node_name}"),
                        "waste_var": self.model.NewIntVar(0, f_value, f"waste_{node_name}"),
                    }
                    
                    max_sharing_vol = min(f_value, Config.MAX_SHARING_VOLUME or f_value)
                    
                    # 共有変数の作成
                    for key in z3_node.get("intra_sharing_vars", {}).keys():
                        share_name = f"share_intra_t{target_idx}_l{level}_k{node_idx}_{key}"
                        node_vars["intra_sharing_vars"][key] = self.model.NewIntVar(0, max_sharing_vol, share_name)
                    
                    for key in z3_node.get("inter_sharing_vars", {}).keys():
                        share_name = f"share_inter_t{target_idx}_l{level}_k{node_idx}_{key}"
                        node_vars["inter_sharing_vars"][key] = self.model.NewIntVar(0, max_sharing_vol, share_name)
                    
                    level_nodes.append(node_vars)
                tree_data[level] = level_nodes
            self.forest_vars.append(tree_data)
            
        # 2. ピア(R)ノード変数の定義
        for i, z3_peer_node in enumerate(self.problem.peer_nodes):
            name = z3_peer_node["name"]
            p_val = z3_peer_node["p_value"]
            is_generic = z3_peer_node.get("is_generic", False)

            node_vars = {
                "name": name,
                "p_value": p_val,
                "is_generic": is_generic,
                "ratio_vars": [
                    self.model.NewIntVar(0, p_val, f"ratio_{name}_r{t}")
                    for t in range(self.problem.num_reagents)
                ],
                "total_input_var": self.model.NewIntVar(0, 2, f"TotalInput_{name}"),
                "is_active_var": self.model.NewBoolVar(f"IsActive_{name}"),
                "waste_var": self.model.NewIntVar(0, 2, f"waste_{name}"),
                "incoming_bools": {} # 逆引き用: (target, level, node) -> BoolVar/IntVar
            }

            if is_generic:
                candidates = z3_peer_node["candidate_sources"]
                num_candidates = len(candidates)
                
                # 入力元を選択するためのインデックス変数
                # 0 ~ num_candidates-1: 候補のインデックス
                # num_candidates: 選択なし(ダミー)
                idx1 = self.model.NewIntVar(0, num_candidates, f"src_idx1_{name}")
                idx2 = self.model.NewIntVar(0, num_candidates, f"src_idx2_{name}")
                
                node_vars["input_indices"] = [idx1, idx2]
                node_vars["candidate_sources"] = candidates
                node_vars["input_vars"] = {} 

                # Generic Peerの選択状態を表すBoolVarを事前生成
                # ここで論理制約(OnlyEnforceIf)を使って、インデックスとフラグをリンクさせる
                for c_idx, src_id in enumerate(candidates):
                    is_sel = self.model.NewBoolVar(f"is_sel_{name}_from_{src_id}")
                    
                    # idx1 == c_idx または idx2 == c_idx ならば is_sel は True
                    b1 = self.model.NewBoolVar(f"b1_{name}_{src_id}")
                    b2 = self.model.NewBoolVar(f"b2_{name}_{src_id}")
                    
                    # idx1 == c_idx <=> b1
                    self.model.Add(idx1 == c_idx).OnlyEnforceIf(b1)
                    self.model.Add(idx1 != c_idx).OnlyEnforceIf(b1.Not())
                    
                    # idx2 == c_idx <=> b2
                    self.model.Add(idx2 == c_idx).OnlyEnforceIf(b2)
                    self.model.Add(idx2 != c_idx).OnlyEnforceIf(b2.Not())
                    
                    # is_sel <=> (b1 or b2)
                    # CP-SATでは BoolOr を OnlyEnforceIf で制御可能
                    self.model.AddBoolOr([b1, b2]).OnlyEnforceIf(is_sel)
                    self.model.AddImplication(b1, is_sel)
                    self.model.AddImplication(b2, is_sel)
                    # どちらもFalseなら is_sel も False
                    self.model.AddBoolAnd([b1.Not(), b2.Not()]).OnlyEnforceIf(is_sel.Not())
                    
                    node_vars["incoming_bools"][src_id] = is_sel
                
            else:
                # 固定ペア (Fixed Peer)
                node_vars["source_a_id"] = z3_peer_node["source_a_id"]
                node_vars["source_b_id"] = z3_peer_node["source_b_id"]
                node_vars["input_vars"] = {
                    "from_a": self.model.NewIntVar(0, 1, f"share_peer_a_to_{name}"),
                    "from_b": self.model.NewIntVar(0, 1, f"share_peer_b_to_{name}"),
                }
                # 固定ペアもincoming_boolsに登録（汎用的な取得のため）
                node_vars["incoming_bools"][node_vars["source_a_id"]] = node_vars["input_vars"]["from_a"]
                node_vars["incoming_bools"][node_vars["source_b_id"]] = node_vars["input_vars"]["from_b"]

            self.peer_vars.append(node_vars)

    # --- ヘルパーメソッド ---

    def _get_input_vars(self, node_vars):
        """ノードへの全入力変数を取得（試薬 + Intra + Inter）"""
        return (
            node_vars.get("reagent_vars", [])
            + list(node_vars.get("intra_sharing_vars", {}).values())
            + list(node_vars.get("inter_sharing_vars", {}).values())
        )

    def _get_outgoing_vars(self, src_target_idx, src_level, src_node_idx):
        """あるノードから出ていく全共有変数を取得（下流DFMM + Peerへの供給）"""
        outgoing = []
        key_intra = f"from_{create_intra_key(src_level, src_node_idx)}"
        key_inter = f"from_{create_inter_key(src_target_idx, src_level, src_node_idx)}"
       
        # 1. DFMMノードへの供給を探索
        for dst_target_idx, tree_dst in enumerate(self.forest_vars):
            for dst_level, level_dst in tree_dst.items():
                for dst_node_idx, node_dst in enumerate(level_dst):
                    if src_target_idx == dst_target_idx and key_intra in node_dst.get("intra_sharing_vars", {}):
                        outgoing.append(node_dst["intra_sharing_vars"][key_intra])
                    elif src_target_idx != dst_target_idx and key_inter in node_dst.get("inter_sharing_vars", {}):
                        outgoing.append(node_dst["inter_sharing_vars"][key_inter])
       
        # 2. Peerノードへの供給を探索
        src_id = (src_target_idx, src_level, src_node_idx)
        for or_peer_node in self.peer_vars:
            if src_id in or_peer_node.get("incoming_bools", {}):
                outgoing.append(or_peer_node["incoming_bools"][src_id])
                    
        return outgoing

    def _get_outgoing_vars_from_peer(self, peer_node_index):
        """Peerノードから出ていく変数を取得"""
        outgoing = []
        key_inter = f"from_{create_peer_key(peer_node_index)}"
        for dst_target_idx, tree_dst in enumerate(self.forest_vars):
            for dst_level, level_dst in tree_dst.items():
                for dst_node_idx, node_dst in enumerate(level_dst):
                    if key_inter in node_dst.get("inter_sharing_vars", {}):
                        outgoing.append(node_dst["inter_sharing_vars"][key_inter])
        return outgoing

    def _iterate_all_nodes(self):
        """全DFMMノードをイテレートするジェネレータ"""
        for target_idx, tree in enumerate(self.forest_vars):
            for level, nodes in tree.items():
                for node_idx, node in enumerate(nodes):
                    yield target_idx, level, node_idx, node

    # --- 制約メソッド ---

    def _set_initial_constraints(self):
        """ルートノードの濃度比率をターゲット定義に固定"""
        for target_idx, target in enumerate(self.problem.targets_config):
            # level=0, node_idx=0 がルートと仮定
            if 0 in self.forest_vars[target_idx] and self.forest_vars[target_idx][0]:
                root_vars = self.forest_vars[target_idx][0][0]
                for reagent_idx in range(self.problem.num_reagents):
                    self.model.Add(root_vars["ratio_vars"][reagent_idx] == target["ratios"][reagent_idx])

    def _set_conservation_constraints(self):
        """質量保存則: 生産量 == 全入力の和"""
        for m_src, l_src, k_src, node_vars in self._iterate_all_nodes():
            total_produced = node_vars["total_input_var"]
            self.model.Add(total_produced == sum(self._get_input_vars(node_vars)))

    def _set_concentration_constraints(self):
        """濃度保存則: ターゲット濃度 * 量 == ソース濃度 * 量 の総和"""
        for dst_target_idx, dst_level, dst_node_idx, node_vars in self._iterate_all_nodes():
            p_dst = self.problem.p_value_maps[dst_target_idx][(dst_level, dst_node_idx)]
            f_dst = self.problem.targets_config[dst_target_idx]["factors"][dst_level]
            node_name_prefix = f"t{dst_target_idx}l{dst_level}k{dst_node_idx}"

            for reagent_idx in range(self.problem.num_reagents):
                # 左辺: 目標濃度比率 * スケール係数
                lhs = f_dst * node_vars["ratio_vars"][reagent_idx]
                rhs_terms = []
                
                # 1. 直接投入試薬からの寄与 (濃度=p_dst相当として扱う簡易モデルの場合、あるいは純粋試薬として扱う場合など
                # ここのロジックは問題定義に依存しますが、元のコードに従い p_dst * volume としています)
                rhs_terms.append(p_dst * node_vars["reagent_vars"][reagent_idx])
                
                # 2. Intra Sharing (内部共有) からの寄与
                for key, w_var in node_vars.get("intra_sharing_vars", {}).items():
                    key_no_prefix = key.replace("from_", "")
                    parsed = parse_sharing_key(key_no_prefix)
                    l, k = parsed["level"], parsed["node_idx"]
                    
                    r_src = self.forest_vars[dst_target_idx][l][k]["ratio_vars"][reagent_idx]
                    p_src = self.problem.p_value_maps[dst_target_idx][(l, k)]
                    f_src = self.problem.targets_config[dst_target_idx]["factors"][l]
                    max_w = min(f_src, Config.MAX_SHARING_VOLUME or f_src)
                    
                    # 積 (Ratio * Volume) は非線形なので、中間変数 prod を導入
                    # prod = r_src * w_var
                    prod = self.model.NewIntVar(0, p_src * max_w, f"P_intra_{node_name_prefix}_r{reagent_idx}_{key}")
                    self.model.AddMultiplicationEquality(prod, [r_src, w_var])
                    
                    # スケール合わせ: prod * (p_dst / p_src)
                    # 整数演算のため、割り切れることを前提か、近似を使用
                    rhs_terms.append(prod * (p_dst // p_src))

                # 3. Inter Sharing (外部共有) からの寄与
                for key, w_var in node_vars.get("inter_sharing_vars", {}).items():
                    key_no_prefix = key.replace("from_", "")
                    parsed = parse_sharing_key(key_no_prefix)
                    
                    if parsed["type"] == "PEER":
                        peer = self.peer_vars[parsed["idx"]]
                        r_src = peer["ratio_vars"][reagent_idx]
                        p_src = peer["p_value"]
                        max_w = 2 # Peerからの供給は通常少量
                    else:
                        m, l, k = parsed["target_idx"], parsed["level"], parsed["node_idx"]
                        r_src = self.forest_vars[m][l][k]["ratio_vars"][reagent_idx]
                        p_src = self.problem.p_value_maps[m][(l, k)]
                        f_src = self.problem.targets_config[m]["factors"][l]
                        max_w = min(f_src, Config.MAX_SHARING_VOLUME or f_src)
                    
                    prod = self.model.NewIntVar(0, p_src * max_w, f"P_inter_{node_name_prefix}_r{reagent_idx}_{key}")
                    self.model.AddMultiplicationEquality(prod, [r_src, w_var])
                    rhs_terms.append(prod * (p_dst // p_src))

                self.model.Add(lhs == sum(rhs_terms))

    def _set_ratio_sum_constraints(self):
        """比率変数の総和が p_node に等しい（正規化条件）"""
        for target_idx, level, node_idx, node_vars in self._iterate_all_nodes():
            p_node = self.problem.p_value_maps[target_idx][(level, node_idx)]
            is_active = node_vars["is_active_var"]
            
            # アクティブな場合のみ総和制約を適用
            self.model.Add(sum(node_vars["ratio_vars"]) == p_node).OnlyEnforceIf(is_active)
            
            # 非アクティブなら比率はすべて0
            for r_var in node_vars["ratio_vars"]:
                self.model.Add(r_var == 0).OnlyEnforceIf(is_active.Not())

    def _set_leaf_node_constraints(self):
        """葉ノード（p=f）の場合、比率は試薬量そのものになる制約"""
        for target_idx, level, node_idx, node_vars in self._iterate_all_nodes():
            p_node = self.problem.p_value_maps[target_idx][(level, node_idx)]
            f_node = self.problem.targets_config[target_idx]["factors"][level]
            
            if p_node == f_node:
                for t in range(self.problem.num_reagents):
                    self.model.Add(node_vars["ratio_vars"][t] == node_vars["reagent_vars"][t])

    def _set_mixer_capacity_constraints(self):
        """ミキサー容量制約: レベル0は固定量、それ以外はアクティブなら固定量"""
        for target_idx, level, node_idx, node_vars in self._iterate_all_nodes():
            f_value = self.problem.targets_config[target_idx]["factors"][level]
            total_sum = node_vars["total_input_var"]
            is_active = node_vars["is_active_var"]
            
            if level == 0:
                # ルートは常に必要
                self.model.Add(total_sum == f_value)
                self.model.Add(is_active == 1) # ルートは常にアクティブ
            else:
                self.model.Add(total_sum == f_value).OnlyEnforceIf(is_active)
                self.model.Add(total_sum == 0).OnlyEnforceIf(is_active.Not())

    def _set_activity_constraints(self):
        """アクティビティ制約: 誰かに供給しているならアクティブである必要がある"""
        # DFMM Nodes
        for (src_target_idx, src_level, src_node_idx, node_vars) in self._iterate_all_nodes():
            if src_level == 0: continue # ルートは上記で固定済み
            
            total_used = sum(self._get_outgoing_vars(src_target_idx, src_level, src_node_idx))
            is_active = node_vars["is_active_var"]
            
            # Output >= 1 ==> Active
            self.model.Add(total_used >= 1).OnlyEnforceIf(is_active)
            # Not Active ==> Output == 0
            self.model.Add(total_used == 0).OnlyEnforceIf(is_active.Not())
        
        # Peer Nodes
        for i, or_peer_node in enumerate(self.peer_vars):
            total_used = sum(self._get_outgoing_vars_from_peer(i))
            is_active = or_peer_node["is_active_var"]
            
            self.model.Add(total_used >= 1).OnlyEnforceIf(is_active)
            self.model.Add(total_used == 0).OnlyEnforceIf(is_active.Not())

    def _set_peer_mixing_constraints(self):
        """Peerノードの混合ロジック"""
        for i, or_peer_node in enumerate(self.peer_vars):
            if or_peer_node.get("is_generic"):
                self._set_dynamic_peer_constraints(or_peer_node)
            else:
                self._set_fixed_peer_constraints(or_peer_node)

    def _set_dynamic_peer_constraints(self, or_peer_node):
        """Generic Peer: 候補リストから2つ選んで混合"""
        is_active = or_peer_node["is_active_var"]
        idx1, idx2 = or_peer_node["input_indices"]
        candidates = or_peer_node["candidate_sources"]
        num_candidates = len(candidates)
        
        DUMMY_IDX = num_candidates 
        
        # インデックス範囲制約
        self.model.Add(idx1 < num_candidates).OnlyEnforceIf(is_active)
        self.model.Add(idx2 < num_candidates).OnlyEnforceIf(is_active)
        self.model.Add(idx1 < idx2).OnlyEnforceIf(is_active) # 対称性排除も兼ねて idx1 < idx2
        
        self.model.Add(idx1 == DUMMY_IDX).OnlyEnforceIf(is_active.Not())
        self.model.Add(idx2 == DUMMY_IDX).OnlyEnforceIf(is_active.Not())

        # 容量固定
        self.model.Add(or_peer_node["total_input_var"] == 2).OnlyEnforceIf(is_active)
        self.model.Add(or_peer_node["total_input_var"] == 0).OnlyEnforceIf(is_active.Not())

        # 濃度計算: AddElement を使用して選択されたソースの濃度を取得
        for reagent_idx in range(self.problem.num_reagents):
            candidate_ratio_vars = []
            for (m, l, k) in candidates:
                src_var = self.forest_vars[m][l][k]["ratio_vars"][reagent_idx]
                candidate_ratio_vars.append(src_var)
            # ダミー選択時（非アクティブ）は0
            candidate_ratio_vars.append(self.model.NewConstant(0))
            
            val1 = self.model.NewIntVar(0, or_peer_node["p_value"], f"val1_{or_peer_node['name']}_r{reagent_idx}")
            self.model.AddElement(idx1, candidate_ratio_vars, val1)
            
            val2 = self.model.NewIntVar(0, or_peer_node["p_value"], f"val2_{or_peer_node['name']}_r{reagent_idx}")
            self.model.AddElement(idx2, candidate_ratio_vars, val2)
            
            # Peerでの混合: (Source1 + Source2) = 2 * PeerRatio
            self.model.Add(2 * or_peer_node["ratio_vars"][reagent_idx] == val1 + val2)

        # 比率総和制約
        self.model.Add(sum(or_peer_node["ratio_vars"]) == or_peer_node["p_value"]).OnlyEnforceIf(is_active)
        self.model.Add(sum(or_peer_node["ratio_vars"]) == 0).OnlyEnforceIf(is_active.Not())

    def _set_fixed_peer_constraints(self, or_peer_node):
        """Fixed Peer: 指定された2つのソースから混合"""
        total_input = or_peer_node["total_input_var"]
        is_active = or_peer_node["is_active_var"]
        w_a = or_peer_node["input_vars"]["from_a"]
        w_b = or_peer_node["input_vars"]["from_b"]

        self.model.Add(total_input == w_a + w_b)
        self.model.Add(w_a == 1).OnlyEnforceIf(is_active)
        self.model.Add(w_b == 1).OnlyEnforceIf(is_active)
        
        # 非アクティブ時は0
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
        
        for t in range(self.problem.num_reagents):
            self.model.Add(2 * r_new_vars[t] == r_a_vars[t] + r_b_vars[t]).OnlyEnforceIf(is_active)

    def _set_input_degree_constraints(self):
        """Fan-in制約: 1つのノードに入る異なる共有ソースの数を制限"""
        max_fan_in = getattr(Config, "MAX_SHARED_INPUTS", None)
        if max_fan_in is None: return

        print(f"--- Setting max shared input types (Fan-in) per node to {max_fan_in} ---")

        # DFMM Nodes
        for _, _, _, node_vars in self._iterate_all_nodes():
            sharing_vars = []
            sharing_vars.extend(node_vars.get("intra_sharing_vars", {}).values())
            sharing_vars.extend(node_vars.get("inter_sharing_vars", {}).values())
            if not sharing_vars: continue

            # 値が > 0 の変数の数をカウント
            is_used_bools = []
            for var in sharing_vars:
                is_used = self.model.NewBoolVar(f"is_used_{var.Name()}")
                self.model.Add(var > 0).OnlyEnforceIf(is_used)
                self.model.Add(var == 0).OnlyEnforceIf(is_used.Not())
                is_used_bools.append(is_used)
            self.model.Add(sum(is_used_bools) <= max_fan_in)
        
        # Generic Peers (常に2入力なので、Fan-in < 2 なら使用禁止)
        if max_fan_in < 2:
            for peer in self.peer_vars:
                if peer.get("is_generic"):
                    self.model.Add(peer["is_active_var"] == 0)

    def _set_symmetry_breaking_constraints(self):
        """対称性排除: 同一レベル・同一スペックのノード間の順序を固定"""
        # 1. DFMM Nodes
        for m, tree_vars in enumerate(self.forest_vars):
            for l, nodes_vars_list in tree_vars.items():
                if len(nodes_vars_list) > 1:
                    for k in range(len(nodes_vars_list) - 1):
                        node_k = nodes_vars_list[k]
                        node_k1 = nodes_vars_list[k+1]
                        # アクティブ状態の順序付け: Active(k) >= Active(k+1)
                        # つまり、前が非アクティブなら後ろも非アクティブ
                        self.model.Add(node_k["is_active_var"] >= node_k1["is_active_var"])
                        # 同じアクティブ状態なら、生産量で順序付け（オプション）
                        self.model.Add(node_k["total_input_var"] >= node_k1["total_input_var"])

        # 2. Generic Peer Nodes
        peers_by_p = defaultdict(list)
        for p_var in self.peer_vars:
            if p_var.get("is_generic"):
                peers_by_p[p_var["p_value"]].append(p_var)
        
        for p_val, peers in peers_by_p.items():
            if len(peers) > 1:
                for i in range(len(peers) - 1):
                    peer_k = peers[i]
                    peer_k1 = peers[i+1]
                    self.model.Add(peer_k["is_active_var"] >= peer_k1["is_active_var"])
                    
                    # 両方アクティブなら、使用するソースインデックスで辞書順にするなど
                    idx1_k = peer_k["input_indices"][0]
                    idx1_k1 = peer_k1["input_indices"][0]
                    self.model.Add(idx1_k <= idx1_k1).OnlyEnforceIf(peer_k1["is_active_var"])

    def _set_max_reagent_input_per_node_constraint(self):
        """1ノードあたりの最大試薬投入量（ソフト制約）"""
        max_limit = Config.MAX_TOTAL_REAGENT_INPUT_PER_NODE
        if max_limit is None or max_limit <= 0: return

        print(f"--- Setting max total reagent input per node (Soft Constraint) to {max_limit} ---")
        self.all_reagent_excess_vars = []
        
        for target_idx, level, node_idx, node_vars in self._iterate_all_nodes():
            reagent_vars = node_vars.get("reagent_vars", [])
            if reagent_vars:
                # 変数の上限値は適当なマージンを持たせる
                p_node = self.problem.p_value_maps[target_idx][(level, node_idx)]
                var_limit = max(p_node * 2, 2000)
                
                total = self.model.NewIntVar(0, var_limit, f"total_reagent_{target_idx}_{level}_{node_idx}")
                self.model.Add(total == sum(reagent_vars))
                
                # Excess = max(0, total - max_limit)
                excess = self.model.NewIntVar(0, var_limit, f"excess_{target_idx}_{level}_{node_idx}")
                
                # excess >= total - max_limit
                self.model.Add(excess >= total - max_limit)
                # excess >= 0 (ドメインで保証済み)
                
                # NOTE: ここで Minimize(excess) することで、excessは可能な限り小さくなる（実質 max(0, ...) となる）
                self.all_reagent_excess_vars.append(excess)

    def _set_objective_function(self):
        """目的関数の設定"""
        all_waste_vars = []
        all_activity_vars = []
        all_reagent_vars = []

        # DFMMノードの廃棄量計算
        for (src_target_idx, src_level, src_node_idx, node_vars) in self._iterate_all_nodes():
            if src_level != 0:
                total_prod = node_vars["total_input_var"]
                total_used = sum(self._get_outgoing_vars(src_target_idx, src_level, src_node_idx))
                waste_var = node_vars["waste_var"]
                # Waste = Production - Used
                self.model.Add(waste_var == total_prod - total_used)
                all_waste_vars.append(waste_var)
            all_activity_vars.append(node_vars["is_active_var"])
            all_reagent_vars.extend(node_vars.get("reagent_vars", []))

        # Peerノードの廃棄量計算
        for i, or_peer_node in enumerate(self.peer_vars):
            total_prod = or_peer_node["total_input_var"]
            total_used = sum(self._get_outgoing_vars_from_peer(i))
            waste_var = or_peer_node["waste_var"]
            self.model.Add(waste_var == total_prod - total_used)
            all_waste_vars.append(waste_var)
            all_activity_vars.append(or_peer_node["is_active_var"])

        total_waste = sum(all_waste_vars)
        
        # ハード制約: Wasteは負にならない（定義上変数は0以上だが、論理的な整合性として）
        if self.objective_mode == "waste":
            # 自明な解（何も作らない）を避けるための最小制約などを必要に応じて追加
            self.model.Add(total_waste >= 1)
        
        total_operations = sum(all_activity_vars)
        total_reagents = sum(all_reagent_vars)

        # ペナルティ（ソフト制約）の加算
        penalty_weight = 1000 
        total_penalty = 0
        if self.all_reagent_excess_vars:
            total_penalty = sum(self.all_reagent_excess_vars) * penalty_weight

        # 最小化の実行
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

    def _set_search_strategy(self):
        """探索戦略（ヒューリスティック）の指定"""
        # アクティブ変数を優先的に決定する戦略
        # これにより、不要な枝刈りが早まることを期待
        all_active_vars = []
        
        # DFMM
        for tree in self.forest_vars:
            for level in tree.values():
                for node in level:
                    all_active_vars.append(node["is_active_var"])
        
        # Peer
        for peer in self.peer_vars:
            all_active_vars.append(peer["is_active_var"])
            if peer.get("is_generic"):
                 # Generic Peerのソース選択も早めに分岐させる
                 all_active_vars.extend(peer["input_indices"])

        # 戦略の登録
        self.model.AddDecisionStrategy(
            all_active_vars,
            cp_model.CHOOSE_FIRST,
            cp_model.SELECT_MIN_VALUE # まずは非アクティブ(0)を試す、あるいはMAX_VALUE(1)でアクティブを試すか等は問題による
        )

# core/or_tools_solver.py (テクニック適用・互換性維持版)
import time
import sys
from ortools.sat.python import cp_model  # Or-Tools の CP-SAT ソルバーをインポート
from utils.config_loader import Config
from utils import (    
    create_dfmm_node_name,
    create_intra_key,
    create_inter_key,
    create_peer_key,
    parse_sharing_key,
)

# Pythonの再帰深度の上限を増やす (深いツリー構造での制約設定に対応するため)
sys.setrecursionlimit(2000)
# 掛け算の制約 (AddMultiplicationEquality) で使用する変数の中間的な上限値
MAX_PRODUCT_BOUND = 50000

class OrToolsSolutionModel:
    """
    Or-Toolsソルバーが見つけた「解」を保持し、
    SolutionReporter（レポート生成クラス）が要求する形式で
    データを抽出・提供する責務を持つラッパークラス。
    
    ソルバーが解を見つけた後、このクラスのインスタンスが生成されます。
    """

    def __init__(self, problem, solver, forest_vars, peer_vars):
        """
        コンストラクタ。
        
        Args:
            problem (MTWMProblem): 解の元となった問題定義
            solver (cp_model.CpSolver): 解を見つけたソルバー本体
            forest_vars (list): 解が決定された Or-Tools の「変数」 (DFMMノード)
            peer_vars (list): 解が決定された Or-Tools の「変数」 (ピアRノード)
        """
        self.problem = problem
        self.solver = solver
        self.forest_vars = forest_vars
        self.peer_vars = peer_vars
        self.num_reagents = problem.num_reagents

    def _v(self, or_tools_var):
        """
        ヘルパーメソッド: Or-Toolsの変数値を取得します。
        ソルバーの `Value()` メソッドを呼び出し、Noneの場合は0を返します。
        """
        val = self.solver.Value(or_tools_var)
        return int(val) if val is not None else 0

    def analyze(self):
        """
        `SolutionReporter` のために、解（ソルバーの変数）を分析し、
        レポート生成に必要な情報を辞書形式で構築します。
        
        Returns:
            dict: 分析結果 (総操作回数, 廃棄物量, 試薬使用量, 各ノードの詳細...)
        """
        results = {
            "total_operations": 0,       # 総混合操作回数
            "total_reagent_units": 0,  # 総試薬使用量
            "total_waste": 0,            # 総廃棄物量 (目的が 'waste' 以外の場合、ここで計算)
            "reagent_usage": {},         # 試薬ごとの使用量
            "nodes_details": [],         # 各ノードの混合詳細
        }

        # 1. DFMMノードの分析
        for target_idx, tree in enumerate(self.forest_vars):
            for level, nodes in tree.items():
                for node_idx, node_vars in enumerate(nodes):
                    # このノードの総入力
                    total_input = self._v(node_vars["total_input_var"])
                    if total_input == 0:
                        continue  # このノードは使われなかったのでスキップ

                    results["total_operations"] += 1  # 操作回数をカウント
                    
                    # 試薬使用量を集計
                    reagent_vals = [self._v(r) for r in node_vars["reagent_vars"]]
                    for r_idx, val in enumerate(reagent_vals):
                        if val > 0:
                            results["total_reagent_units"] += val
                            results["reagent_usage"][r_idx] = (
                                results["reagent_usage"].get(r_idx, 0) + val
                            )
                    
                    # 廃棄物量を集計 (level 0 (root) 以外)
                    if level != 0:
                        results["total_waste"] += self._v(node_vars["waste_var"])
                    
                    node_name = create_dfmm_node_name(target_idx, level, node_idx)
                    
                    # レポート用の詳細情報を追加
                    results["nodes_details"].append(
                        {
                            "target_id": target_idx,
                            "level": level,
                            "name": node_name,
                            "total_input": total_input,
                            "ratio_composition": [  # このノードの最終的な比率
                                self._v(r) for r in node_vars["ratio_vars"]
                            ],
                            "mixing_str": self._generate_mixing_description( # 混合の詳細文字列
                                node_vars, target_idx
                            ),
                        }
                    )

        # 2. ピア(R)ノードの分析
        for i, peer_node_vars in enumerate(self.peer_vars):
            total_input = self._v(peer_node_vars["total_input_var"])
            if total_input == 0:
                continue # このピア(R)ノードは使われなかった

            results["total_operations"] += 1 # 操作回数をカウント
            results["total_waste"] += self._v(peer_node_vars["waste_var"]) # 廃棄物量を集計

            # ピア(R)ノードの材料(A, B)のノード名を取得
            z3_peer_node = self.problem.peer_nodes[i]
            m_a, l_a, k_a = z3_peer_node["source_a_id"]
            name_a = create_dfmm_node_name(m_a, l_a, k_a)
            m_b, l_b, k_b = z3_peer_node["source_b_id"]
            name_b = create_dfmm_node_name(m_b, l_b, k_b)
            mixing_str = f"1 x {name_a} + 1 x {name_b}" # 1:1 混合
            level_eff = (l_a + l_b) / 2.0 - 0.5 # グラフ表示用の実効レベル

            # レポート用の詳細情報を追加
            results["nodes_details"].append(
                {
                    "target_id": -1, # ピア(R)ノードはターゲットID -1 (共有ノード) とする
                    "level": level_eff,
                    "name": peer_node_vars["name"],
                    "total_input": total_input,
                    "ratio_composition": [
                        self._v(r) for r in peer_node_vars["ratio_vars"]
                    ],
                    "mixing_str": mixing_str,
                }
            )

        # レポートが見やすくなるよう、ターゲットIDとレベルでソート
        results["nodes_details"].sort(key=lambda x: (x["target_id"], x["level"]))
        return results

    def _generate_mixing_description(self, node_vars, target_idx):
        """
        特定のノードについて、解の変数値から「何と何をどれだけ混ぜたか」
        という説明文字列を生成します。 (例: "2 x Reagent1 + 3 x mixer_t1_l1_k0")
        
        Args:
            node_vars (dict): 解が決定された Or-Tools のノード変数辞書
            target_idx (int): このノードのターゲットID (ツリー内共有の解析用)
            
        Returns:
            str: 混合の詳細文字列
        """
        desc = []
        
        # 1. 試薬の投入
        for r_idx, r_var in enumerate(node_vars.get("reagent_vars", [])):
            if (val := self._v(r_var)) > 0:
                desc.append(f"{val} x Reagent{r_idx+1}")
                
        # 2. ツリー内(Intra)共有
        for key, w_var in node_vars.get("intra_sharing_vars", {}).items():
            if (val := self._v(w_var)) > 0:
                key_no_prefix = key.replace("from_", "") # "from_l1k0" -> "l1k0"
                parsed = parse_sharing_key(key_no_prefix) # -> {"type": "INTRA", "level": 1, "node_idx": 0}
                node_name = create_dfmm_node_name(
                    target_idx, parsed["level"], parsed["node_idx"]
                )
                desc.append(f"{val} x {node_name}")
                
        # 3. ツリー間(Inter)共有
        for key, w_var in node_vars.get("inter_sharing_vars", {}).items():
            if (val := self._v(w_var)) > 0:
                key_no_prefix = key.replace("from_", "") # "from_t1_l1k0" or "from_R_idx0"
                parsed = parse_sharing_key(key_no_prefix)
                
                if parsed["type"] == "PEER":
                    # 供給元がピア(R)ノードの場合
                    peer_node_name = self.problem.peer_nodes[parsed["idx"]]["name"]
                    desc.append(f"{val} x {peer_node_name}")
                elif parsed["type"] == "DFMM":
                    # 供給元が別ツリーのDFMMノードの場合
                    node_name = create_dfmm_node_name(
                        parsed["target_idx"], parsed["level"], parsed["node_idx"]
                    )
                    desc.append(f"{val} x {node_name}")
                    
        return " + ".join(desc)


# ==============================================================================
#  OrToolsSolver クラス
# ==============================================================================

class OrToolsSolver:
    """
    MTWMProblem を Or-Tools CP-SAT モデルに変換し、最適化を実行するクラス。
    """

    def __init__(self, problem, objective_mode="waste"):
        """
        コンストラクタ。
        インスタンス化の時点で、Or-Tools のモデルと変数を定義し、
        全ての制約を追加します。
        
        Args:
            problem (MTWMProblem): `core/problem.py` で定義された問題オブジェクト
            objective_mode (str): 最適化の目的 ('waste', 'operations', 'reagents')
        """
        self.problem = problem
        self.objective_mode = objective_mode
        self.model = cp_model.CpModel()     # Or-Tools のモデル本体
        self.solver = cp_model.CpSolver()   # Or-Tools のソルバー本体
        
        # --- テクニック適用 (MAX_CPU_WORKERS の使用) ---
        if Config.MAX_CPU_WORKERS is not None and Config.MAX_CPU_WORKERS > 0:
            print(f"--- Limiting solver CPU workers to {Config.MAX_CPU_WORKERS} ---")
            self.solver.parameters.num_workers = Config.MAX_CPU_WORKERS # (原文では num_search_workers)
            
        # --- テクニック適用 (探索ログの有効化) ---
        self.solver.parameters.log_search_progress = True
            
        self.forest_vars = []             # Or-Tools の DFMM ノード変数を格納
        self.peer_vars = []               # Or-Tools の ピアR ノード変数を格納
        
        # --- モデル構築の実行 ---
        # 1. Or-Tools の変数を定義
        # 2. 全ての制約をモデルに追加
        # 3. 目的関数を設定
        self._set_variables_and_constraints()

    def solve(self):
        """
        構築されたモデルに対して最適化を実行します。
        
        Returns:
            tuple: (best_model, best_value, best_analysis, elapsed_time)
                   best_model: OrToolsSolutionModel (解のラッパー)
                   best_value: 目的変数の最適値
                   best_analysis: 解の分析結果辞書
                   elapsed_time: 計算時間
        """
        start_time = time.time()
        print(
            f"\n--- Solving the optimization problem (mode: {self.objective_mode.upper()}) with Or-Tools CP-SAT ---"
        )
        
        # --- テクニック適用 (コールバックの代わりに、ログ有効化で進捗表示) ---
        # --- 最適化実行 ---
        status = self.solver.Solve(self.model)
        
        elapsed_time = time.time() - start_time
        best_model = None
        best_value = None
        best_analysis = None

        # --- 結果の判定 ---
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            # 最適解または実行可能解が見つかった場合
            best_value = self.solver.ObjectiveValue()
            print(
                f"Or-Tools found an optimal solution with {self.objective_mode}: {int(best_value)}"
            )
            
            # 解をラップする OrToolsSolutionModel を生成
            best_model = OrToolsSolutionModel(
                self.problem, self.solver, self.forest_vars, self.peer_vars
            )
            
            # 解の分析を実行
            best_analysis = best_model.analyze()
        else:
            # 解が見つからなかった場合
            print(f"Or-Tools Solver status: {self.solver.StatusName(status)}")
            if status == cp_model.INFEASIBLE:
                print("No feasible solution found.")
                
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
        # --- テクニック適用 (_set_range_constraints の呼び出しを削除) ---
        # self._set_range_constraints() 
        self._set_activity_constraints()
        self._set_peer_mixing_constraints()
        
        # --- テクニック適用 (対称性の破壊) ---
        self._set_symmetry_breaking_constraints()
        
        self.objective_variable = self._set_objective_function()

    def _define_or_tools_variables(self):
        """
        `core/problem.py` (Z3変数) の構造に基づき、
        Or-Tools (CP-SAT) の変数を定義し、`self.forest_vars` と
        `self.peer_vars` に格納します。
        
        --- テクニック適用: 変数上限の厳密化 ---
        """
            
        # 1. DFMMノード変数の定義
        # (self.problem.forest (Z3) の構造をイテレート)
        for target_idx, z3_tree in enumerate(self.problem.forest):
            tree_data = {}
            for level, z3_nodes in z3_tree.items():
                level_nodes = []
                for node_idx, z3_node in enumerate(z3_nodes):
                    node_name = create_dfmm_node_name(target_idx, level, node_idx)
                    
                    # --- テクニック適用 (厳密な上限値の取得) ---
                    p_node = self.problem.p_value_maps[target_idx][(level, node_idx)]
                    f_value = self.problem.targets_config[target_idx]["factors"][level]
                    reagent_max = max(0, f_value - 1)
                    
                    # Or-Tools の変数を生成
                    node_vars = {
                        "ratio_vars": [ # 比率 (r_i)
                            self.model.NewIntVar(
                                0, p_node, f"ratio_{node_name}_r{t}" # 上限: MAX_BOUND -> p_node
                            )
                            for t in range(self.problem.num_reagents)
                        ],
                        "reagent_vars": [ # 試薬投入量 (w_r_i)
                            self.model.NewIntVar(
                                0, reagent_max, f"reagent_vol_{node_name}_r{t}" # 上限: MAX_BOUND -> reagent_max
                            )
                            for t in range(self.problem.num_reagents)
                        ],
                        "intra_sharing_vars": {}, # ツリー内共有 (w_intra)
                        "inter_sharing_vars": {}, # ツリー間共有 (w_inter)
                        "total_input_var": self.model.NewIntVar( # 総入力 (W_total)
                            0, f_value, f"TotalInput_{node_name}" # 上限: MAX_BOUND -> f_value
                        ),
                        "is_active_var": self.model.NewBoolVar(f"IsActive_{node_name}"), # ノードが使われているか (Bool)
                        "waste_var": self.model.NewIntVar( # 廃棄物量 (w_waste)
                            0, f_value, f"waste_{node_name}" # 上限: MAX_BOUND -> f_value
                        ),
                    }
                    
                    # 共有量の上限を設定
                    # (テクニック適用: f_value と MAX_SHARING_VOLUME の小さい方)
                    max_sharing_vol = min(f_value, Config.MAX_SHARING_VOLUME or f_value)
                    
                    # ツリー内(Intra)共有変数を定義
                    for key in z3_node.get("intra_sharing_vars", {}).keys():
                        share_name = (
                            f"share_intra_t{target_idx}_l{level}_k{node_idx}_{key}"
                        )
                        node_vars["intra_sharing_vars"][key] = self.model.NewIntVar(
                            0, max_sharing_vol, share_name # 上限: max_sharing_vol (厳密化後)
                        )
                    # ツリー間(Inter)共有変数を定義
                    for key in z3_node.get("inter_sharing_vars", {}).keys():
                        share_name = (
                            f"share_inter_t{target_idx}_l{level}_k{node_idx}_{key}"
                        )
                        node_vars["inter_sharing_vars"][key] = self.model.NewIntVar(
                            0, max_sharing_vol, share_name # 上限: max_sharing_vol (厳密化後)
                        )
                    level_nodes.append(node_vars)
                tree_data[level] = level_nodes
            self.forest_vars.append(tree_data)
            
        # 2. ピア(R)ノード変数の定義
        # (self.problem.peer_nodes (Z3) の構造をイテレート)
        # (ピア(R)ノードの上限値は元から厳密だったため、変更なし)
        for i, z3_peer_node in enumerate(self.problem.peer_nodes):
            name = z3_peer_node["name"]
            p_val = z3_peer_node["p_value"]
            node_vars = {
                "name": name,
                "p_value": p_val,
                "source_a_id": z3_peer_node["source_a_id"],
                "source_b_id": z3_peer_node["source_b_id"],
                "ratio_vars": [ # 比率 (r_i)
                    self.model.NewIntVar(0, p_val, f"ratio_{name}_r{t}")
                    for t in range(self.problem.num_reagents)
                ],
                "input_vars": { # 1:1 混合の入力 (w_a, w_b) (0 or 1)
                    "from_a": self.model.NewIntVar(0, 1, f"share_peer_a_to_{name}"),
                    "from_b": self.model.NewIntVar(0, 1, f"share_peer_b_to_{name}"),
                },
                "total_input_var": self.model.NewIntVar(0, 2, f"TotalInput_{name}"), # 総入力 (0 or 2)
                "is_active_var": self.model.NewBoolVar(f"IsActive_{name}"), # 使われているか
                "waste_var": self.model.NewIntVar(0, 2, f"waste_{name}"), # 廃棄物量
            }
            self.peer_vars.append(node_vars)

    # --- ヘルパーメソッド (制約設定で使用) ---

    def _get_input_vars(self, node_vars):
        """特定のDFMMノードへの全入力変数(試薬 + 共有)のリストを返す"""
        return (
            node_vars.get("reagent_vars", [])
            + list(node_vars.get("intra_sharing_vars", {}).values())
            + list(node_vars.get("inter_sharing_vars", {}).values())
        )

    def _get_outgoing_vars(self, src_target_idx, src_level, src_node_idx):
        """特定のDFMMノードから出ていく全出力変数(共有)のリストを返す"""
        outgoing = []
        key_intra = f"from_{create_intra_key(src_level, src_node_idx)}"
        key_inter = f"from_{create_inter_key(src_target_idx, src_level, src_node_idx)}"
        
        # 全DFMMノード (供給先) をチェック
        for dst_target_idx, tree_dst in enumerate(self.forest_vars):
            for dst_level, level_dst in tree_dst.items():
                for dst_node_idx, node_dst in enumerate(level_dst):
                    # ツリー内共有
                    if src_target_idx == dst_target_idx and key_intra in node_dst.get(
                        "intra_sharing_vars", {}
                    ):
                        outgoing.append(node_dst["intra_sharing_vars"][key_intra])
                    # ツリー間共有
                    elif src_target_idx != dst_target_idx and key_inter in node_dst.get(
                        "inter_sharing_vars", {}
                    ):
                        outgoing.append(node_dst["inter_sharing_vars"][key_inter])
        
        # 全ピア(R)ノード (供給先) をチェック
        for or_peer_node in self.peer_vars:
            if (
                src_target_idx,
                src_level,
                src_node_idx,
            ) == or_peer_node["source_a_id"]:
                outgoing.append(or_peer_node["input_vars"]["from_a"])
            if (
                src_target_idx,
                src_level,
                src_node_idx,
            ) == or_peer_node["source_b_id"]:
                outgoing.append(or_peer_node["input_vars"]["from_b"])
        return outgoing

    def _get_outgoing_vars_from_peer(self, peer_node_index):
        """特定のピア(R)ノードから出ていく全出力変数(共有)のリストを返す"""
        outgoing = []
        key_inter = f"from_{create_peer_key(peer_node_index)}"
        
        # 全DFMMノード (供給先) をチェック
        for dst_target_idx, tree_dst in enumerate(self.forest_vars):
            for dst_level, level_dst in tree_dst.items():
                for dst_node_idx, node_dst in enumerate(level_dst):
                    if key_inter in node_dst.get("inter_sharing_vars", {}):
                        outgoing.append(node_dst["inter_sharing_vars"][key_inter])
        return outgoing

    def _iterate_all_nodes(self):
        """全DFMMノードをイテレートするヘルパージェネレータ"""
        for target_idx, tree in enumerate(self.forest_vars):
            for level, nodes in tree.items():
                for node_idx, node in enumerate(nodes):
                    yield target_idx, level, node_idx, node

    # --- 制約 (Constraints) 設定メソッド ---

    def _set_initial_constraints(self):
        """[制約1] 最終ターゲット(root, level 0)の比率は、設定値と一致しなければならない"""
        for target_idx, target in enumerate(self.problem.targets_config):
            root_vars = self.forest_vars[target_idx][0][0] # level 0, node 0
            for reagent_idx in range(self.problem.num_reagents):
                # (例: root.ratio_vars[0] == 1)
                self.model.Add(
                    root_vars["ratio_vars"][reagent_idx]
                    == target["ratios"][reagent_idx]
                )

    def _set_conservation_constraints(self):
        """[制約2] 流量保存則: TotalInput = sum(全ての入力)"""
        for m_src, l_src, k_src, node_vars in self._iterate_all_nodes():
            total_produced = node_vars["total_input_var"]
            # (例: W_total == w_r1 + w_r2 + w_intra_... + w_inter_...)
            self.model.Add(total_produced == sum(self._get_input_vars(node_vars)))

    def _set_concentration_constraints(self):
        """[制約3] 濃度保存則 (混合方程式)
           f_dst * r_dst_i = sum( (P_dst / P_src) * r_src_i * w_src )
        """
        for (
            dst_target_idx,
            dst_level,
            dst_node_idx,
            node_vars,
        ) in self._iterate_all_nodes():
            p_dst = self.problem.p_value_maps[dst_target_idx][(dst_level, dst_node_idx)]
            f_dst = self.problem.targets_config[dst_target_idx]["factors"][dst_level]

            # 試薬ごと (i) に制約を追加
            for reagent_idx in range(self.problem.num_reagents):
                # --- 左辺 (LHS) ---
                lhs = f_dst * node_vars["ratio_vars"][reagent_idx] # f_dst * r_dst_i
                
                # --- 右辺 (RHS) ---
                rhs_terms = []
                
                # (A) 試薬からの入力
                # (P_dst / P_src_reagent) * r_src_reagent * w_src_reagent
                #   r_src_reagent = 1 (試薬iのみ1, 他は0)
                #   P_src_reagent = 1 (試薬のP値は1)
                # -> P_dst * 1 * w_reagent_i
                rhs_terms.append(p_dst * node_vars["reagent_vars"][reagent_idx])

                # (B) ツリー内共有からの入力
                for key, w_var in node_vars.get("intra_sharing_vars", {}).items():
                    key_no_prefix = key.replace("from_", "")
                    parsed_key = parse_sharing_key(key_no_prefix)
                    l_src = parsed_key["level"]
                    k_src = parsed_key["node_idx"]
                    r_src = self.forest_vars[dst_target_idx][l_src][k_src][
                        "ratio_vars"
                    ][reagent_idx] # r_src_i
                    p_src = self.problem.p_value_maps[dst_target_idx][(l_src, k_src)] # P_src
                    
                    # (r_src * w_var) の掛け算を行うための中間変数
                    prod_name = f"Prod_intra_t{dst_target_idx}l{dst_level}k{dst_node_idx}_r{reagent_idx}_from_{key}"
                    product_var = self.model.NewIntVar(0, MAX_PRODUCT_BOUND, prod_name)
                    self.model.AddMultiplicationEquality(product_var, [r_src, w_var])
                    
                    scale_factor = p_dst // p_src # (P_dst / P_src)
                    rhs_terms.append(product_var * scale_factor)

                # (C) ツリー間共有からの入力
                for key, w_var in node_vars.get("inter_sharing_vars", {}).items():
                    key_no_prefix = key.replace("from_", "")
                    parsed_key = parse_sharing_key(key_no_prefix)
                    if parsed_key["type"] == "PEER":
                        # (C-1) ピア(R)ノードからの入力
                        r_node_idx = parsed_key["idx"]
                        or_peer_node = self.peer_vars[r_node_idx]
                        r_src = or_peer_node["ratio_vars"][reagent_idx] # r_src_i
                        p_src = or_peer_node["p_value"] # P_src
                    else:
                        # (C-2) DFMMノードからの入力
                        m_src = parsed_key["target_idx"]
                        l_src = parsed_key["level"]
                        k_src = parsed_key["node_idx"]
                        r_src = self.forest_vars[m_src][l_src][k_src]["ratio_vars"][
                            reagent_idx
                        ] # r_src_i
                        p_src = self.problem.p_value_maps[m_src][(l_src, k_src)] # P_src
                    
                    prod_name = f"Prod_inter_t{dst_target_idx}l{dst_level}k{dst_node_idx}_r{reagent_idx}_from_{key}"
                    product_var = self.model.NewIntVar(0, MAX_PRODUCT_BOUND, prod_name)
                    self.model.AddMultiplicationEquality(product_var, [r_src, w_var])
                    
                    scale_factor = p_dst // p_src # (P_dst / P_src)
                    rhs_terms.append(product_var * scale_factor)
                
                # --- 制約を追加 ---
                # (LHS == sum(RHS))
                self.model.Add(lhs == sum(rhs_terms))

    def _set_ratio_sum_constraints(self):
        """[制約4] 各ノードの比率の合計値は、そのノードのP値と一致しなければならない"""
        for target_idx, level, node_idx, node_vars in self._iterate_all_nodes():
            p_node = self.problem.p_value_maps[target_idx][(level, node_idx)]
            # (例: r1 + r2 + r3 == P_node)
            self.model.Add(sum(node_vars["ratio_vars"]) == p_node)

    def _set_leaf_node_constraints(self):
        """[制約5] リーフノード(試薬のみで構成されるノード)の制約
           (P値 == Factor値 となるノード)
           r_i = w_reagent_i
        """
        for target_idx, level, node_idx, node_vars in self._iterate_all_nodes():
            p_node = self.problem.p_value_maps[target_idx][(level, node_idx)]
            f_node = self.problem.targets_config[target_idx]["factors"][level]
            if p_node == f_node:
                # このノードはリーフノード
                for reagent_idx in range(self.problem.num_reagents):
                    self.model.Add(
                        node_vars["ratio_vars"][reagent_idx]
                        == node_vars["reagent_vars"][reagent_idx]
                    )

    def _set_mixer_capacity_constraints(self):
        """[制約6] ミキサー容量の制約
           TotalInput == Factor (そのレベルの因数)
        """
        for target_idx, level, node_idx, node_vars in self._iterate_all_nodes():
            f_value = self.problem.targets_config[target_idx]["factors"][level]
            total_sum = node_vars["total_input_var"]
            is_active = node_vars["is_active_var"]
            
            if level == 0:
                # rootノードは常にアクティブで、TotalInput == Factor
                self.model.Add(total_sum == f_value)
            else:
                # root以外のノードは、アクティブ(is_active=True)の場合のみ制約を適用
                # (is_active=True) => (TotalInput == f_value)
                self.model.Add(total_sum == f_value).OnlyEnforceIf(is_active)
                # (is_active=False) => (TotalInput == 0)
                self.model.Add(total_sum == 0).OnlyEnforceIf(is_active.Not())

    def _set_range_constraints(self):
        """[制約7] 試薬投入量の上限
           w_reagent_i <= Factor - 1
           (TotalInput が Factor なので、1種類の試薬が Factor 以上になることはない)
           
           (テクニック適用により、このメソッドは冗長になったが、
            元のファイルの構造を維持するため残しておく)
           (ただし、_define_or_tools_variables で厳密化されたため、呼び出しは不要)
        """
        pass # (呼び出されない)

    def _set_activity_constraints(self):
        """[制約8] ノードのアクティビティ制約
           ノードがアクティブ(TotalInput > 0) => ノードが使用される(TotalUsed > 0)
        """
        # (A) DFMMノード (root以外)
        for (
            src_target_idx,
            src_level,
            src_node_idx,
            node_vars,
        ) in self._iterate_all_nodes():
            if src_level == 0:
                continue # rootノードはスキップ
                
            total_prod = node_vars["total_input_var"] # このノードの総生産量
            total_used = sum( # このノードの総使用量 (出力の合計)
                self._get_outgoing_vars(src_target_idx, src_level, src_node_idx)
            )
            is_active = node_vars["is_active_var"] # (TotalInput > 0) を示す変数
            
            is_used_name = f"IsUsed_t{src_target_idx}_l{src_level}_k{src_node_idx}"
            is_used = self.model.NewBoolVar(is_used_name) # (TotalUsed > 0) を示す変数
            
            self.model.Add(total_used >= 1).OnlyEnforceIf(is_used)
            self.model.Add(total_used == 0).OnlyEnforceIf(is_used.Not())
            
            # (is_active=True) => (is_used=True)
            # (生産されたら、必ず使われなければならない (廃棄は別で計算))
            self.model.AddImplication(is_active, is_used)
            
        # (B) ピア(R)ノード
        for i, or_peer_node in enumerate(self.peer_vars):
            total_prod = or_peer_node["total_input_var"]
            total_used = sum(self._get_outgoing_vars_from_peer(i))
            is_active = or_peer_node["is_active_var"]
            is_used = self.model.NewBoolVar(f"IsUsed_Peer_{i}")
            
            self.model.Add(total_used >= 1).OnlyEnforceIf(is_used)
            self.model.Add(total_used == 0).OnlyEnforceIf(is_used.Not())
            self.model.AddImplication(is_active, is_used)

    def _set_peer_mixing_constraints(self):
        """[制約9] ピア(R)ノードの混合制約
           (★ Big-M法 を使用するように [9e] を修正)
        """
        
        # Big-M法で使用する「十分に大きなM」を定義
        # P値の最大値 (p_val) は、(MAX_MIXER_SIZE ^ N_LEVELS) 程度になる可能性がある
        # 余裕を持たせて MAX_PRODUCT_BOUND (50000) をMとして使用する
        BIG_M = MAX_PRODUCT_BOUND 

        for i, or_peer_node in enumerate(self.peer_vars):
            total_input = or_peer_node["total_input_var"]
            is_active = or_peer_node["is_active_var"] # (is_active は BoolVar (0 or 1))
            w_a = or_peer_node["input_vars"]["from_a"] 
            w_b = or_peer_node["input_vars"]["from_b"] 

            # [9a] TotalInput = w_a + w_b
            self.model.Add(total_input == w_a + w_b)

            # [9b] アクティブな場合 (is_active=True)
            self.model.Add(total_input == 2).OnlyEnforceIf(is_active)
            self.model.Add(w_a == 1).OnlyEnforceIf(is_active)
            self.model.Add(w_b == 1).OnlyEnforceIf(is_active)

            # [9c] 非アクティブな場合 (is_active=False)
            self.model.Add(total_input == 0).OnlyEnforceIf(is_active.Not())
            self.model.Add(w_a == 0).OnlyEnforceIf(is_active.Not())
            self.model.Add(w_b == 0).OnlyEnforceIf(is_active.Not())

            # [9d] ピア(R)ノードの比率の合計
            p_val = or_peer_node["p_value"]
            r_new_vars = or_peer_node["ratio_vars"]
            self.model.Add(sum(r_new_vars) == p_val).OnlyEnforceIf(is_active)
            self.model.Add(sum(r_new_vars) == 0).OnlyEnforceIf(is_active.Not())
            
            # [9e] ピア(R)ノードの濃度保存則 (1:1混合)
            #    2 * r_new_i = r_a_i + r_b_i
            #    (★ Big-M法を適用)
            #    is_active=1 => (lhs == rhs)
            #    is_active=0 => 制約は無効 (LHSもRHSも 0 になるため)
            
            m_a, l_a, k_a = or_peer_node["source_a_id"]
            r_a_vars = self.forest_vars[m_a][l_a][k_a]["ratio_vars"]
            m_b, l_b, k_b = or_peer_node["source_b_id"]
            r_b_vars = self.forest_vars[m_b][l_b][k_b]["ratio_vars"]
            
            for reagent_idx in range(self.problem.num_reagents):
                lhs = 2 * r_new_vars[reagent_idx]
                rhs = r_a_vars[reagent_idx] + r_b_vars[reagent_idx]

                # (is_active=1 の場合)
                # (lhs - rhs <= 0)  (つまり lhs <= rhs)
                self.model.Add(lhs - rhs <= BIG_M * (1 - is_active))
                # (lhs - rhs >= 0)  (つまり lhs >= rhs)
                self.model.Add(lhs - rhs >= -BIG_M * (1 - is_active))
                
                # (is_active=0 の場合)
                # (lhs <= BIG_M) (r_new_vars[reagent_idx]は 0 になるため lhs=0)
                # (lhs >= -BIG_M) (r_a_vars, r_b_vars も 0 (または非アクティブノード) のはずだが、
                #  念のため rhs も 0 になるよう制約を追加する)
                # (r_new_vars[reagent_idx] == 0).OnlyEnforceIf(is_active.Not()) 
                # (↑ [9d]の (sum(r_new_vars) == 0).OnlyEnforceIf(is_active.Not()) でカバーされる)

    # --- テクニック適用 (対称性の破壊メソッドの追加) ---
    def _set_symmetry_breaking_constraints(self):
        """
        *** テクニック適用: 対称性の破壊 ***
        同じターゲットの同じレベルにあるノード間で、
        総入力（または活動状態）に順序付けを行う。
        """
        for m, tree_vars in enumerate(self.forest_vars):
            for l, nodes_vars_list in tree_vars.items():
                # (nodes_vars_list は、そのレベルのノード変数の辞書のリスト)
                if len(nodes_vars_list) > 1:
                    for k in range(len(nodes_vars_list) - 1):
                        # k番目のノードの総入力変数
                        total_input_k = nodes_vars_list[k]['total_input_var']
                        # k+1番目のノードの総入力変数
                        total_input_k1 = nodes_vars_list[k+1]['total_input_var']
                        
                        # total_input_k >= total_input_k1 という制約を追加
                        self.model.Add(total_input_k >= total_input_k1)

    def _set_objective_function(self):
        """[制約10] 目的関数 (最小化の対象) を定義する"""

        all_waste_vars = []      # 全ての廃棄物変数
        all_activity_vars = []   # 全てのアクティビティ変数 (操作回数)
        all_reagent_vars = []    # 全ての試薬投入変数

        # 1. DFMMノードの集計
        for (
            src_target_idx,
            src_level,
            src_node_idx,
            node_vars,
        ) in self._iterate_all_nodes():
            if src_level != 0:
                # root ノード以外
                total_prod = node_vars["total_input_var"] # 総生産量
                total_used = sum( # 総使用量
                    self._get_outgoing_vars(src_target_idx, src_level, src_node_idx)
                )
                waste_var = node_vars["waste_var"]
                
                # [10a] 廃棄物 = 生産量 - 使用量
                self.model.Add(waste_var == total_prod - total_used)
                all_waste_vars.append(waste_var)

            all_activity_vars.append(node_vars["is_active_var"])
            all_reagent_vars.extend(node_vars.get("reagent_vars", []))

        # 2. ピア(R)ノードの集計
        for i, or_peer_node in enumerate(self.peer_vars):
            total_prod = or_peer_node["total_input_var"]
            total_used = sum(self._get_outgoing_vars_from_peer(i))
            waste_var = or_peer_node["waste_var"]
            
            # [10b] 廃棄物 = 生産量 - 使用量
            self.model.Add(waste_var == total_prod - total_used)
            all_waste_vars.append(waste_var)
            all_activity_vars.append(or_peer_node["is_active_var"])

        # 3. 目的変数の設定 
        total_waste = sum(all_waste_vars)
        total_operations = sum(all_activity_vars)
        total_reagents = sum(all_reagent_vars)

        if self.objective_mode == "waste":
            # [目的1] 総廃棄物量を最小化
            self.model.Minimize(total_waste)
            return total_waste
        elif self.objective_mode == "operations":
            # [目的2] 総操作回数を最小化
            self.model.Minimize(total_operations)
            return total_operations
        elif self.objective_mode == "reagents":
            # [目的3] 総試薬使用量を最小化
            self.model.Minimize(total_reagents)
            return total_reagents
        else:
            raise ValueError(
                f"Unknown optimization mode: '{self.objective_mode}'. Must be 'waste', 'operations', or 'reagents'."
            )

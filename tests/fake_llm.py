"""按节点路由的假 LLM —— 让 M2 全链能在无网络、零成本下跑 UT。

路由靠 prompt 里的「# 角色」段：每个节点的 _ROLE 都不同，据此返回对应
schema 的合法 JSON。dispatch 是有状态的（每场演 2 拍后收场），否则不收敛。
"""

from __future__ import annotations

import json
import re

from story_engine.llm.base import Completion

_SCENE_RE = re.compile(r"c\d+\.s\d+")


def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


class ScriptedProvider:
    """满足 LLMProvider 协议；走 LLMClient 的手搓 parse 路径（不需要 instructor）。"""

    model = "fake-story"

    def __init__(self, beats_per_scene: int = 2) -> None:
        self.beats_per_scene = beats_per_scene
        self.dispatch_counts: dict[str, int] = {}
        self.roles_seen: list[str] = []

    def complete(self, prompt: str, **cfg: object) -> Completion:
        role = prompt.split("\n")[1] if "\n" in prompt else prompt
        self.roles_seen.append(role)
        text = self._route(role, prompt)
        return Completion(
            text=text,
            prompt_tokens=max(1, len(prompt) // 4),
            completion_tokens=max(1, len(text) // 4),
            model=self.model,
        )

    # ── 路由 ────────────────────────────────────────────────────
    def _route(self, role: str, prompt: str) -> str:
        if "总纲师" in role:
            return self._architect()
        if "首卷脊骨规划师" in role:
            return self._expand_spine()
        if "首卷分章规划师" in role:
            return self._expand_beats()
        if "人物设计师" in role:
            return self._seed_profiles()
        if "世界构建师" in role:
            return self._worldbuilder(prompt)
        if "分章规划师" in role:
            return self._planner()
        if "卷复盘" in role:
            return self._replanner(prompt)
        if "导演" in role:
            return self._setup(prompt)
        if "现场调度" in role:
            return self._dispatch(prompt)
        if "演员" in role:
            return self._character()
        if "小说家" in role:
            return "叶凡踏入青云门时，天光正落在石阶上。他抬头，看见了那道熟悉的身影。"
        if "记录员" in role:
            return self._extractor(prompt)
        if "摘要员" in role:
            return self._summarizer(prompt)
        if "校验员" in role:
            return self._entailment(prompt)
        if "档案管理员" in role:
            return self._reconciler(prompt)
        if "续写评审" in role:
            return _j({"findings": []})
        return "{}"

    # ── 各节点产物 ──────────────────────────────────────────────
    def _architect(self) -> str:
        return _j({
            "l0": {
                "logline": "荒古后裔叶凡踏上成仙路",
                "genre": ["东方玄幻"],
                "tone": ["悲壮"],
                "core_dramatic_question": "成仙是否值得",
                "ending_intent": "揭穿成仙真相",
                "protagonist_arc_intent": ["变强", "护同伴"],
            },
            "l1": {
                "version": 1,
                "volumes": [{"vol_id": "v1", "title": "第一卷"}],
                "threads": [{"thread_id": "main_road", "tier": "main", "desc": "成仙路"}],
                "character_arcs": [
                    {"char_id": "ye_fan", "from_state": "山村少年", "to_state": "执灯人"}
                ],
                "foreshadow_map": [{"fs_id": "origin", "desc": "身世伏笔"}],
                "world_refs": ["concept.cultivation", "loc.qing_yun"],
            },
        })

    def _expand_spine(self) -> str:
        return _j({
            "goal": "叶凡拜入青云门并初窥修行",
            "thread_targets": [
                {"thread_id": "main_road", "target_milestone": "入门"},
                {"thread_id": "th.not_exists", "target_milestone": "应被过滤"},
            ],
            "foreshadow_due": [{"fs_id": "origin", "action": "plant"}],
            "volume_spine": {
                "shared_pressure": "青云门考核在即，外来者必须证明自己",
                "inciting": "叶凡报名考核，退路切断",
                "midpoint": "考核中身世线索暴露",
                "climax": "获准入门，秘密与代价落下",
            },
        })

    def _expand_beats(self) -> str:
        return _j({
            "chapter_beats": [
                {
                    "planned_seq": 3,  # 乱序：系统应重排连号
                    "event": "叶凡叩山门，考核令已下",
                    "leaves_open": ["at_gate"],
                    "inherits": ["spine.shared_pressure"],
                    "touches_spine": "pressure",
                    "pov_focus": ["char.ye_fan"],
                },
                {
                    "planned_seq": 1,
                    "event": "报名时被点名质疑，退路切断",
                    "leaves_open": ["in_trial"],
                    "inherits": ["at_gate"],
                    "touches_spine": "inciting",
                    "pov_focus": ["char.ye_fan"],
                },
                {
                    "planned_seq": 2,
                    "event": "考核中旧物被认出，局面质变",
                    "leaves_open": ["secret_seen"],
                    "inherits": ["in_trial"],
                    "touches_spine": "midpoint",
                    "pov_focus": ["char.ye_fan"],
                },
                {
                    "planned_seq": 4,
                    "event": "闯过终关获准入门，代价落下",
                    "leaves_open": ["admitted_cost"],
                    "inherits": ["secret_seen"],
                    "touches_spine": "climax",
                    "pov_focus": ["char.ye_fan"],
                },
            ],
        })

    def _seed_profiles(self) -> str:
        return _j({
            "entries": [
                {"type": "trait", "scope": "ye_fan", "text": "外柔内韧，认死理"},
                {
                    "type": "goal", "scope": "char.ye_fan", "text": "变强护同伴",
                    "goal_kind": "long-drive",
                },
                {
                    "type": "voice", "scope": "char.ye_fan", "text": "话少，句短",
                    "example": "我要拜入青云门。",
                },
                {"type": "trait", "scope": "char.long_tao", "text": "龙套，应被过滤"},
            ]
        })

    def _worldbuilder(self, prompt: str) -> str:
        refs = ["concept.cultivation", "loc.qing_yun"]
        return _j({
            "entities": [
                {
                    "id": r,
                    "canonical_name": r.split(".")[-1],
                    "tier": "core",
                    "origin": "seeded",
                    "definition": f"{r} 的权威定义。",
                }
                for r in refs
            ]
        })

    def _planner(self) -> str:
        return _j({
            "chapter": "c1",
            "derived_from": {"l2_vol_id": "v1", "l1_thread_ids": [], "l1_fs_ids": []},
            "theme": "少年入门",
            "tone": "热血",
            "chapter_goal": "叶凡拜入青云门",
            "thread_advances": [{"thread_id": "th.main_road", "intent": "踏出第一步"}],
            "foreshadow_ops": [{"fs_id": "fs.origin", "op": "PLANT", "reason": "organic"}],
            "cast": [{"char_id": "char.ye_fan", "role_in_chapter": "主角", "required": True}],
            "story_beats": [{"seq": 1, "gist": "叩门"}, {"seq": 2, "gist": "受试"}],
            "constraints": ["不得提前揭穿 fs.origin"],
        })

    def _setup(self, prompt: str) -> str:
        return _j({
            "chapter": "c1",
            "scenes": [{
                "scene_id": "c1.s1",
                "location": "loc.qing_yun",
                "pov": "char.ye_fan",
                "goal": "叩开山门",
                "conflict": "门规阻拦",
                "cast": [
                    {"char": "char.ye_fan", "entry_state": "风尘仆仆", "scene_goal": "求入门"},
                    {"char": "char.pang_bo", "entry_state": "守在阶前"},
                ],
                "obligations": [
                    {"obligation_id": "o1", "desc": "叶凡表明来意"},
                    {"obligation_id": "o2", "desc": "庞博点破他的身份", "precede": ["o1"]},
                ],
                "exit_when": ["叶凡获准入门"],
                "budget": {"max_beats": 6},
            }],
        })

    def _dispatch(self, prompt: str) -> str:
        m = _SCENE_RE.search(prompt)
        scene = m.group(0) if m else "c?.s?"
        done = self.dispatch_counts.get(scene, 0)
        if done >= self.beats_per_scene:
            return _j({"close_scene": True, "reason": "承重拍已全部命中"})
        self.dispatch_counts[scene] = done + 1
        return _j({
            "close_scene": False,
            "owner": "char.ye_fan" if done == 0 else "char.pang_bo",
            "dramatic_goal": "表明来意" if done == 0 else "点破身份",
            "hits": f"{scene}.o{done + 1}",
        })

    def _character(self) -> str:
        return _j({
            "type": "dialogue",
            "dialogue": {"line": "我要拜入青云门。", "subtext": "别无退路", "tone": "沉稳"},
            "handoff": {"kind": "DEMAND", "target": "char.pang_bo"},
        })

    def _extractor(self, prompt: str) -> str:
        chapter = 2 if "第 2 章" in prompt else 1
        return _j({
            "chapter": chapter,
            "mem_ops": [
                {
                    "action": "ADD",
                    "type": "fact",
                    "scope": "char.ye_fan",
                    "text": "叶凡拜入青云门",
                    "evidence": [{"chapter": chapter, "scene": 1, "beats": [1, 1]}],
                },
                {
                    "action": "ADD",
                    "type": "fact",
                    "scope": "char.ye_fan",
                    "text": "证据指向不存在的拍",
                    "evidence": [{"chapter": chapter, "scene": 9, "beats": [9, 9]}],
                },
            ],
            "arc_ops": [],
        })

    def _summarizer(self, prompt: str) -> str:
        chapter = 2 if "第 2 章" in prompt else 1
        cid = f"c{chapter}"
        sid = f"{cid}.s1"
        return _j({
            "entries": [
                {
                    "level": "scene",
                    "ref": sid,
                    "text": "叶凡叩门求试。",
                    "cast": ["char.ye_fan"],
                    "threads": ["th.main_road"],
                    "covers": [{"chapter": chapter, "scene": 1}],
                },
                {
                    "level": "chapter",
                    "ref": cid,
                    "text": "叶凡拜入青云门，立下志向。",
                    "cast": ["char.ye_fan"],
                    "threads": ["th.main_road"],
                    "covers": [{"chapter": chapter}],
                },
            ]
        })

    def _replanner(self, prompt: str) -> str:
        return _j({
            "drift_report": {
                "thread_lag": 0.5,
                "foreshadow_overdue_rate": 0.0,
                "violation_density": 0.0,
                "notes": [],
            },
            "action": "hold",
            "volume_summary": {
                "level": "volume",
                "ref": "v1",
                "text": "第一卷：叶凡入门，立下志向。",
                "t_valid": 4,
                "produced_by": "Replanner",
            },
            "loose_ends": [],
            "confirmed_tiers": [],
            "confirmed_emergent": [],
            "world_promote": [],
            "human_gate": None,
        })

    def _entailment(self, prompt: str) -> str:
        return _j({"verdicts": [{"index": 0, "entailed": True}]})

    def _reconciler(self, prompt: str) -> str:
        """第 2 章：旧库里已有同一条事实 → 判 REINFORCE（对账的实测点）。

        目标必须锁定"同一件事"的旧条目（旧库里还有创世 seed 画像，不能瞎指第一条）。
        """
        m = re.search(r'"id":\s*"(m\.[^"]+)"[^}]*"text":\s*"叶凡拜入青云门"', prompt)
        target = m.group(1) if m else None
        if target:
            return _j({
                "mem_ops": [{
                    "action": "REINFORCE",
                    "target_id": target,
                    "evidence": [{"chapter": 2, "scene": 1, "beats": [1, 1]}],
                }]
            })
        # 旧档案里没有同一件事（只有 seed 画像）→ 判 ADD 放行
        ch = re.search(r"第 (\d+) 章", prompt)
        chapter = int(ch.group(1)) if ch else 1
        return _j({
            "mem_ops": [{
                "action": "ADD",
                "type": "fact",
                "scope": "char.ye_fan",
                "text": "叶凡拜入青云门",
                "evidence": [{"chapter": chapter, "scene": 1, "beats": [1, 1]}],
            }]
        })

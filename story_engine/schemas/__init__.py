"""schema 层：pydantic 模型，对应 docs/schema/。"""

from story_engine.schemas.artifacts.chapter_plan import (
    CastMember,
    ChapterPlan,
    ForeshadowOpPlan,
    PlanDerivedFrom,
    StoryBeat,
    ThreadAdvanceIntent,
)
from story_engine.schemas.artifacts.genesis_gap import GenesisGap, GenesisVerdict
from story_engine.schemas.artifacts.recorder_output import (
    ArcOp,
    MemOp,
    RecorderOutput,
    TierNom,
    WorldOp,
)
from story_engine.schemas.artifacts.scene_script import (
    BeatDispatch,
    ContractCast,
    Obligation,
    ObligationBinding,
    SceneBudget,
    SceneContract,
    SceneScript,
)
from story_engine.schemas.artifacts.seed import Seed
from story_engine.schemas.stores.arc import ArcRecord
from story_engine.schemas.stores.memory import MemoryEntry
from story_engine.schemas.stores.plan import L0, L1, L2
from story_engine.schemas.stores.script import (
    Action,
    Beat,
    ChapterScript,
    Dialogue,
    ForeshadowOpRef,
    Handoff,
    Scene,
    SceneCast,
    Thought,
)
from story_engine.schemas.stores.violation import EscalationStep, Locus, Violation
from story_engine.schemas.stores.world import WorldEntity, WorldRelation
from story_engine.schemas.stores.summary import KeyOp, SummaryDelta, SummaryEntry

__all__ = [
    "GenesisGap",
    "GenesisVerdict",
    "ArcOp",
    "MemOp",
    "RecorderOutput",
    "WorldOp",
    "TierNom",
    "Seed",
    "ArcRecord",
    "MemoryEntry",
    "SummaryEntry",
    "SummaryDelta",
    "KeyOp",
    "L0",
    "L1",
    "L2",
    # Script（主真相）
    "Beat",
    "ChapterScript",
    "Scene",
    "SceneCast",
    "Dialogue",
    "Action",
    "Thought",
    "Handoff",
    "ForeshadowOpRef",
    # ChapterPlan（L3）
    "ChapterPlan",
    "PlanDerivedFrom",
    "ThreadAdvanceIntent",
    "ForeshadowOpPlan",
    "CastMember",
    "StoryBeat",
    # SceneScript / 派工
    "SceneScript",
    "SceneContract",
    "Obligation",
    "ObligationBinding",
    "ContractCast",
    "SceneBudget",
    "BeatDispatch",
    "Violation",
    "Locus",
    "EscalationStep",
    "WorldEntity",
    "WorldRelation",
]

"""M5a 离线评估：从 RunRecord / stores 聚合 scorecard，支持 A/B compare。

权威说明见 docs/EVALUATION.md §3.0。
"""

from story_engine.eval.compare import compare_scorecards
from story_engine.eval.scorecard import Scorecard, build_scorecard

__all__ = ["Scorecard", "build_scorecard", "compare_scorecards"]

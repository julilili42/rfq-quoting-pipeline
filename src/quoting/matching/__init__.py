"""Match extracted positions to master data (deterministic)."""
from .matcher import MatchResult, MatchStatus, match_positions

__all__ = ["MatchResult", "MatchStatus", "match_positions"]

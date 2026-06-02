"""News / sentiment overlay (pluggable).

Honest status: there is no live news feed wired in yet, so `get_sentiment`
returns a NEUTRAL score (0.0) — it has no effect on trading. The interface and
no-lookahead feature builder (`research.features.add_news_features`) are in
place; connect a real provider here (e.g. a news API returning per-symbol
sentiment in [-1, 1]) to activate it.
"""

from __future__ import annotations

NEUTRAL = 0.0


async def get_sentiment(symbol: str) -> float:
    """Return a sentiment score in [-1, 1] for `symbol`. Neutral until a real
    news/sentiment provider is connected."""
    # TODO: integrate a documented news/sentiment API and return its score.
    return NEUTRAL


def is_active() -> bool:
    """Whether a real sentiment source is connected (False = neutral stub)."""
    return False

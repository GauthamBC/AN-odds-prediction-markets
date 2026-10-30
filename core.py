"""Typed normalized contracts and low-level probability helpers."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
import json
import math
import re

CATEGORY_NAMES = ("Sports", "Politics", "Entertainment", "Crypto", "Economics", "Science & Tech", "Weather", "Other")

@dataclass
class Quote:
    exchange: str
    market_id: str
    event_id: str
    event_title: str
    question: str
    outcome: str
    probability: float
    category: str
    volume: float
    liquidity: float
    close_at: Optional[str]
    url: str
    rules: str = ""
    type: str = "binary"
    volume_24h: float = 0.0
    image_url: str = ""


def number(value, fallback=0.0):
    try:
        x = float(value)
        return x if math.isfinite(x) else fallback
    except (TypeError, ValueError, OverflowError):
        return fallback


def parse_array(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (ValueError, TypeError):
            return []
    return []


def probability(value):
    if value is None or value == "":
        return None
    p = number(value, float("nan"))
    return p if math.isfinite(p) and 0 <= p <= 1 else None


def midpoint(bid, ask, last=None):
    """Prefer the best available bid/ask midpoint; no fake zero quotes."""
    b, a = probability(bid), probability(ask)
    if b is not None and a is not None and 0 < b <= a < 1:
        return (a + b) / 2
    l = probability(last)
    return l if l is not None and 0 < l < 1 else None


def american(p):
    if p is None:
        return "—"
    if not 0 < p < 1:
        return "—"
    o = 100 * (1-p)/p if p <= .5 else -100*p/(1-p)
    rounded = round(o)
    return f"+{rounded}" if rounded > 0 else str(rounded)


def clean_text(s):
    s = str(s or "").lower().replace("&", " and ")
    s = re.sub(r"\b(?:the|a|an|will|be|to|of|in|on|for|at|by|which|who|is|do|does|win|winner)\b", " ", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def category(text, raw=""):
    t = f"{raw} {text}".lower()
    if any(x in t for x in ("sports", "nfl", "nba", "mlb", "nhl", "soccer", "football", "baseball", "tennis", "ufc", "golf", "f1", "ncaa", "champions league", "super bowl", "premier league", "boxing")):
        return "Sports"
    if any(x in t for x in ("politics", "election", "senate", "congress", "president", "governor", "democrat", "republican", "parliament", "prime minister")):
        return "Politics"
    if any(x in t for x in ("entertainment", "oscars", "grammy", "emmy", "movie", "film", "music", "celebrity", "box office", "tv show")):
        return "Entertainment"
    if any(x in t for x in ("crypto", "bitcoin", "ethereum", "solana", "token", "btc", "eth")):
        return "Crypto"
    if any(x in t for x in ("economics", "economy", "fed rate", "interest rate", "inflation", "cpi", "gdp", "unemployment", "jobs report", "stock market", "s&p 500")):
        return "Economics"
    if any(x in t for x in ("science", "technology", "ai model", "openai", "nasa", "spacex", "robot", "spaceflight")):
        return "Science & Tech"
    if any(x in t for x in ("weather", "hurricane", "tornado", "temperature", "snow", "rainfall", "earthquake")):
        return "Weather"
    return "Other"


def date_from_string(raw):
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def horizon_bucket(days):
    if days is None:
        return "unknown"
    if days <= 1:
        return "0-1d"
    if days <= 7:
        return "2-7d"
    if days <= 30:
        return "8-30d"
    return "31d+"


def remaining_horizon(close_at, now=None):
    d = date_from_string(close_at)
    if d is None:
        return "unknown"
    now = now or datetime.now(timezone.utc)
    return horizon_bucket(max(0, (d - now).total_seconds() / 86400))

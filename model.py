"""Auditable, conservative recency-weighted model; never fabricates historical metrics."""
from __future__ import annotations
from dataclasses import dataclass
from collections import defaultdict
from datetime import datetime, timezone
import csv
import math
from pathlib import Path
from core import Quote, category, date_from_string, horizon_bucket, remaining_horizon, number

HISTORY_START = datetime(2025, 3, 1, tzinfo=timezone.utc)
HALF_LIFE_DAYS = 548.0  # 18 months

@dataclass
class Observation:
    platform: str
    category: str
    event_key: str
    observed_at: datetime
    probability: float
    outcome: int
    horizon: str


def recency_weight(when: datetime, now: datetime):
    return 0.5 ** (max(0., (now - when).total_seconds() / 86400.) / HALF_LIFE_DAYS)


def read_history(path="history.csv", now=None):
    now = now or datetime.now(timezone.utc)
    observations = []
    pth = Path(path)
    if not pth.exists():
        return observations
    with pth.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                when = date_from_string(r.get("observed_at"))
                p = float(r["probability"])
                y = int(r["outcome"])
                platform = r["platform"].strip()
                cat = r["category"].strip()
                if when is None or not HISTORY_START <= when < now or not 0 < p < 1 or y not in (0,1):
                    continue
                if platform not in ("Kalshi", "Polymarket", "Polymarket US"):
                    continue
                if cat not in ("Sports", "Politics", "Entertainment", "Crypto", "Economics", "Science & Tech", "Weather", "Other"):
                    cat = category(cat)
                horizon = r.get("horizon") or horizon_bucket(number(r.get("horizon_days"), 1e6))
                observations.append(Observation(platform, cat, r.get("event_key", ""), when, p, y, horizon))
            except (ValueError, KeyError, OverflowError):
                continue
    return observations


class AccuracyModel:
    def __init__(self, observations=None, now=None):
        self.now = now or datetime.now(timezone.utc)
        self.rows = [x for x in (observations or []) if HISTORY_START <= x.observed_at < self.now]
        self.by_source = defaultdict(list)
        for x in self.rows:
            self.by_source[(x.category, x.horizon, x.platform)].append(x)
            self.by_source[(x.category, "any", x.platform)].append(x)

    def sample(self, category_name, horizon, platform):
        group = self.by_source[(category_name, horizon, platform)]
        if len(group) < 40:
            group = self.by_source[(category_name, "any", platform)]
        return group

    def calibrate(self, platform, p, cat, horizon):
        group = self.sample(cat, horizon, platform)
        if len(group) < 50:
            return p, False
        weighted_error = 0.0
        weight_total = 0.0
        for r in group:
            # Smooth locally around the quoted probability to detect over/under-confidence.
            proximity = math.exp(-.5 * ((r.probability - p)/.13)**2)
            w = recency_weight(r.observed_at, self.now) * proximity
            weight_total += w
            weighted_error += w * (r.outcome - r.probability)
        if weight_total < 18:
            return p, False
        # Shrink corrections; cap at 10 percentage points until validated.
        correction = (weighted_error / weight_total) * (weight_total/(weight_total+65))
        correction = max(-.10, min(.10, correction))
        return max(.005, min(.995, p+correction)), True

    def weights(self, cat, horizon, poly_source="Polymarket"):
        """Compare ONLY same event/outcome at same horizon, with enough distinct pairs."""
        a = self.sample(cat, horizon, "Kalshi")
        b = self.sample(cat, horizon, poly_source)
        def d(rows):
            # Exactly one observation per event/horizon per platform.
            out = {}
            for r in sorted(rows, key=lambda r:r.observed_at):
                if r.event_key:
                    out[r.event_key] = r
            return out
        da, db = d(a), d(b)
        common = da.keys() & db.keys()
        valid = [(da[k], db[k]) for k in common if da[k].outcome == db[k].outcome]
        if len(valid) < 50:
            return .5, .5, len(valid), False
        wa = wb = ea = eb = 0.0
        for ka, pb in valid:
            w = recency_weight(max(ka.observed_at, pb.observed_at), self.now)
            wa += w
            ea += w*(ka.probability-ka.outcome)**2
            eb += w*(pb.probability-pb.outcome)**2
        if wa < 25:
            return .5, .5, len(valid), False
        # Inverse Brier with shrinkage to 50/50, not a direct claim of model superiority.
        ea /= wa
        eb /= wa
        ka_weight = (1/max(ea, .005)) / (1/max(ea,.005) + 1/max(eb,.005))
        strength = min(.65, wa / (wa+200))
        kalshi_w = .5 + (ka_weight - .5)*strength
        return kalshi_w, 1-kalshi_w, len(valid), True

    def predict(self, kalshi: Quote | None, polymarket: Quote | None):
        if not (kalshi and polymarket):
            return {"probability":None, "status":"No cross-market match", "k_weight":None,
                    "p_weight":None,"calibrated":False,"paired_samples":0}
        cat = kalshi.category
        horizon = remaining_horizon(kalshi.close_at or polymarket.close_at, self.now)
        kp, ck = self.calibrate("Kalshi", kalshi.probability, cat, horizon)
        pp, cp = self.calibrate(polymarket.exchange, polymarket.probability, cat, horizon)
        wk, wp, n, qualified = self.weights(cat, horizon, polymarket.exchange)
        forecast = wk*kp+wp*pp
        status = "Historical calibration (experimental)" if (qualified and ck and cp) else (
                 "Partial historical calibration" if (ck or cp or qualified) else "50/50 baseline — unvalidated")
        return {"probability":forecast,"status":status,"k_weight":wk,"p_weight":wp,
                "calibrated":qualified and ck and cp,"paired_samples":n}

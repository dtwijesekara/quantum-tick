"""Score a single signal against real historical candles.

Entry is the OPEN of the candle right after the signal candle (the
earliest no-lookahead entry point). Expiry price is the CLOSE of the
candle at `entry_idx + duration_mins - 1` -- e.g. entry at idx 0,
duration=3min -> expiry at the close of idx 2, exactly 3 minutes later.
Outcome compares the side of entry at expiry (CALL wins iff
expiry > entry), not a touch of some intermediate level -- that's what a
Rise/Fall contract actually pays on.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TradeOutcome:
    entry_open_time: int
    entry_price: float
    expiry_price: float
    contract_type: str
    duration_mins: int
    payout_ratio: float
    outcome: str  # "won" | "lost"
    pnl: float  # per $1 stake, using payout_ratio
    technique: str = ""


def score_signal(
    candles: list[dict],
    entry_idx: int,
    contract_type: str,
    duration_mins: int,
    payout_ratio: float,
    technique: str = "",
) -> TradeOutcome | None:
    """`candles` is the full oldest-first series. `entry_idx` is the index of
    the candle whose OPEN is the entry price. Returns None if there isn't
    enough subsequent history to determine the outcome (trade excluded from
    stats rather than guessed)."""

    expiry_idx = entry_idx + duration_mins - 1
    if expiry_idx >= len(candles) or entry_idx < 0:
        return None

    entry_price = candles[entry_idx]["open"]
    expiry_price = candles[expiry_idx]["close"]

    if contract_type == "CALL":
        won = expiry_price > entry_price
    else:
        won = expiry_price < entry_price

    pnl = payout_ratio if won else -1.0

    return TradeOutcome(
        entry_open_time=candles[entry_idx].get("open_time", candles[entry_idx].get("epoch", 0)),
        entry_price=entry_price,
        expiry_price=expiry_price,
        contract_type=contract_type,
        duration_mins=duration_mins,
        payout_ratio=payout_ratio,
        outcome="won" if won else "lost",
        pnl=pnl,
        technique=technique,
    )

"""Score a single signal against real historical candles.

Entry executes at the OPEN of the candle immediately after the signal
candle (the earliest fair, no-lookahead entry point -- see engine.py for why
sub-candle "late entry" timing can't be simulated from OHLC-only history).

Expiry: a `duration_mins`-minute Rise/Fall contract on 1-minute candles pays
on the price `duration_mins` candles after entry. If entry is the open of
candle at index `entry_idx`, the expiry price is the CLOSE of the candle at
index `entry_idx + duration_mins - 1` (that close *is* the price exactly
`duration_mins` minutes after entry). Worked example: entry at candle idx 0
(covers T..T+60), duration=3min -> expiry at T+180 -> that's the close of
the candle covering T+120..T+180, which is idx 0+3-1=2. Verified against
docs/postmortem/PROJECT_POSTMORTEM.md item 12's warning to hand-check
multi-term arithmetic before trusting it.

Outcome (won/lost) compares the *side of entry* at expiry, not an
intermediate touch -- CALL wins iff expiry_price > entry_price, PUT wins iff
expiry_price < entry_price. This is what a Rise/Fall contract actually pays
on. Scoring against a touch of some intermediate level would be scoring
against a proxy instead of the real payoff (postmortem Checklist B item 6).
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

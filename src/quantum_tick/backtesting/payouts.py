"""Real payout ratios, quoted live from Deriv rather than assumed.

A backtest that assumes a made-up payout ratio can't tell you the real
breakeven line (postmortem Checklist B item 3). We ask Deriv for an actual
`proposal` price per (symbol, duration) and derive payout_ratio =
(payout - stake) / stake from the real quote.
"""

from __future__ import annotations

import logging

from quantum_tick.infrastructure.deriv.client import DerivClient
from quantum_tick.infrastructure.deriv.exceptions import DerivApiError

log = logging.getLogger("quantum_tick.backtesting.payouts")

PayoutTable = dict[tuple[str, int], float]  # (symbol, duration_mins) -> ratio


async def build_payout_table(
    client: DerivClient,
    symbols: list[str],
    durations: list[int],
    currency: str,
    stake: float = 1.0,
) -> PayoutTable:
    table: PayoutTable = {}
    for symbol in symbols:
        for duration in durations:
            try:
                resp = await client.request({
                    "proposal": 1,
                    "amount": stake,
                    "basis": "stake",
                    "contract_type": "CALL",
                    "currency": currency,
                    "duration": duration,
                    "duration_unit": "m",
                    "underlying_symbol": symbol,
                })
            except DerivApiError as exc:
                log.warning("  [%s %dm] proposal failed: %s", symbol, duration, exc)
                continue

            payout = resp["proposal"]["payout"]
            table[(symbol, duration)] = (payout - stake) / stake

    return table


def payout_ratio_for(table: PayoutTable, symbol: str, duration_mins: int, default: float = 0.85) -> float:
    if (symbol, duration_mins) in table:
        return table[(symbol, duration_mins)]
    # fall back to nearest available duration for the same symbol
    same_symbol = {d: r for (s, d), r in table.items() if s == symbol}
    if same_symbol:
        nearest = min(same_symbol, key=lambda d: abs(d - duration_mins))
        return same_symbol[nearest]
    return default

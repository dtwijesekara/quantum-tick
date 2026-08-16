"""Hypothesis: Step Index / Range Break indices use different generation
mechanics than the R_* Volatility indices and were never checked -- flagged
as an untested avenue in docs/research/RESEARCH_FINDINGS.md's "Overall
conclusion".

1. `active_symbols` to find the real symbol codes (never guess these).
2. `contracts_for` on each to confirm Rise/Fall (CALL/PUT) is actually
   offered -- docs/research/RESEARCH_FINDINGS.md found Boom/Crash indices
   have the color bias but *no* Rise/Fall contract at all, so this check is
   not optional.
3. For anything that passes both, fetch real history and run the same
   autocorrelation + runs-test battery as the prior research, so a "new"
   instrument gets the same rigor rather than a shortcut.

Usage: python scripts/research_new_indices.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from quantum_tick.config import get_settings  # noqa: E402
from quantum_tick.domain.candles import is_green  # noqa: E402
from quantum_tick.infrastructure.deriv.auth import AccountBootstrap  # noqa: E402
from quantum_tick.infrastructure.deriv.client import DerivClient  # noqa: E402
from quantum_tick.infrastructure.deriv.exceptions import DerivApiError  # noqa: E402
from quantum_tick.infrastructure.deriv.historical import fetch_history  # noqa: E402
from quantum_tick.research.statistics import autocorrelation, runs_test  # noqa: E402

DAYS = 30
GRANULARITY = 60


TARGET_SUBMARKETS = ("step_index", "range_index", "jump_index", "crash_index")


async def find_candidate_symbols(client: DerivClient) -> list[dict]:
    resp = await client.request({"active_symbols": "brief"})
    symbols = resp.get("active_symbols", [])
    return [s for s in symbols if s.get("submarket") in TARGET_SUBMARKETS]


async def supports_rise_fall(client: DerivClient, symbol: str, currency: str) -> bool:
    try:
        resp = await client.request({"contracts_for": symbol, "currency": currency})
    except DerivApiError:
        return False
    types = {c.get("contract_type") for c in resp.get("contracts_for", {}).get("available", [])}
    return "CALL" in types and "PUT" in types


def analyze(candles: list[dict]) -> None:
    closes = [c["close"] for c in candles]
    returns = [b - a for a, b in zip(closes, closes[1:])]
    directions = [is_green(c) for c in candles]

    n_green = sum(directions)
    pct_green = n_green / len(directions) * 100
    print(f"    n={len(candles)}  %green={pct_green:.2f}%")

    print("    autocorrelation(returns), lags 1-5:", end=" ")
    print([f"{autocorrelation(returns, lag):+.4f}" for lag in range(1, 6)])

    rt = runs_test(directions)
    print(f"    runs test: n1={rt.n1} n2={rt.n2} runs={rt.runs} "
          f"expected={rt.expected_runs:.1f} z={rt.z:.2f} p={rt.p_value:.4f}")


async def main() -> None:
    settings = get_settings()
    bootstrap = AccountBootstrap(
        app_id=settings.deriv_app_id,
        api_token=settings.deriv_api_token,
        account_type=settings.deriv_account_type,
        currency=settings.deriv_currency,
    )
    ws_url = await bootstrap.get_websocket_url()

    async with DerivClient(ws_url) as client:
        candidates = await find_candidate_symbols(client)
        print(f"Found {len(candidates)} candidate symbols (Step/Range Break/Jump/Boom-Crash):")
        for s in candidates:
            print(f"  {s['underlying_symbol']:<12} {s.get('underlying_symbol_name', ''):<28} "
                  f"submarket={s.get('submarket')}")

        tradeable = []
        print("\nChecking Rise/Fall (CALL/PUT) availability...")
        for s in candidates:
            ok = await supports_rise_fall(client, s["underlying_symbol"], settings.deriv_currency)
            print(f"  {s['underlying_symbol']:<12} Rise/Fall offered: {ok}")
            if ok:
                tradeable.append(s)

        if not tradeable:
            print("\nNo Step/Range Break/Jump/Boom-Crash symbol offers Rise/Fall -- "
                  "nothing further to test for this project's contract type.")
            return

        total_count = DAYS * 24 * 60 * 60 // GRANULARITY
        print(f"\nFetching {DAYS} days of history and running the randomness battery "
              f"for each Rise/Fall-eligible symbol...\n")
        for s in tradeable:
            symbol = s["underlying_symbol"]
            print(f"[{symbol}]")
            candles = await fetch_history(client, symbol, GRANULARITY, total_count)
            analyze(candles)
            print()


if __name__ == "__main__":
    asyncio.run(main())

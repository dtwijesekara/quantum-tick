# quantum-tick

Deriv synthetic-indices trading bot: a signal engine (trend + BOS/CHoCH +
ENGULFING/HOP entries, "v8" ruleset), a real-history backtesting engine, and
a live execution service — rebuilt on an N-tier architecture from the
original single-file `dt_bot_v8.py` (kept at [legacy/dt_bot_v8.py](legacy/dt_bot_v8.py)
for reference).

## Why this needed rebuilding, not just a config fix

Deriv now runs two API generations in parallel. The credentials in `.env`
belong to the new "Options API" generation (alphanumeric app_id + `pat_...`
token), which requires a REST → OTP → WebSocket handshake — not the legacy
in-band `authorize` message `dt_bot_v8.py` used. That's why it stopped
connecting. See [docs/postmortem/PROJECT_POSTMORTEM.md](docs/postmortem/PROJECT_POSTMORTEM.md)
items 2–8 for the full diagnosis (written from a previous project, reused
here) and [scripts/diagnose_auth.py](scripts/diagnose_auth.py) for a minimal
script that proves the new flow end to end.

## Architecture (N-tier)

```
src/quantum_tick/
  config/         Settings (pydantic-settings, .env-backed)
  domain/         Pure strategy logic — candles, filters, entries, targets,
                  the master signal engine. No I/O, no logging, fully
                  unit-tested (tests/).
  infrastructure/
    deriv/        REST auth (account bootstrap + OTP), async WebSocket
                  client (req_id-correlated request/response), paginated
                  historical-candle fetch.
  persistence/    SQLAlchemy models + repositories (candle cache, live
                  trades, backtest runs/trades). Session factory is
                  injected, never imported as a global.
  services/       SignalService (logging wrapper over domain/strategy),
                  LiveTradingService (the live scan/trade loop).
  backtesting/    Bar-by-bar replay engine, outcome scoring against real
                  expiry prices, in-sample/out-of-sample stats, reporting.
scripts/          CLI entrypoints: diagnose_auth, fetch_history,
                  run_backtest, run_live.
tests/            Unit tests for the domain/backtesting layers.
docs/postmortem/  Prior integration lessons (imported from this project's
                  own history) — read before touching the Deriv client.
docs/research/    Prior statistical research into whether Deriv synthetic
                  indices have any real directional edge. Read this before
                  trusting any backtest result that looks "too good."
```

## Setup

```bash
python -m venv .venv
./.venv/Scripts/python -m pip install -e ".[dev]"
cp .env.example .env   # fill in real values; .env is gitignored
```

## Usage

```bash
# 1. Prove the auth flow works in isolation (run this first if anything else fails)
python scripts/diagnose_auth.py

# 2. Cache real historical candles for every symbol in .env's SYMBOLS
python scripts/fetch_history.py --days 60

# 3. Backtest the v8 ruleset against that cached history, in-sample/out-of-sample
python scripts/run_backtest.py

# 4. Run the live bot (DRY_RUN=true by default — logs trades, places none)
python scripts/run_live.py
```

`python -m pytest` runs the unit test suite (domain filters, entries,
targets, outcome scoring, pagination boundary math, backtest statistics).

## Safety

- `.env` holds real credentials and is gitignored; `.env.example` is the
  committed template.
- `LiveTradingService` only places real orders when **both**
  `DRY_RUN=false` and `DERIV_ACCOUNT_TYPE=real` — the default is a demo,
  dry-run account that logs what it would have traded.
- Daily loss cap and max-trades-per-day limits carry over unchanged from
  `dt_bot_v8.py` (`MAX_DAILY_LOSS`, `MAX_TRADES_PER_DAY` in `.env`).

## Before trusting a backtest result

This project's own prior research
([docs/research/RESEARCH_FINDINGS.md](docs/research/RESEARCH_FINDINGS.md))
rigorously tested Deriv synthetic-indices direction (autocorrelation, runs
tests, streak continuation, mean reversion, multiple symbols) and found no
statistically real edge anywhere — consistent with Deriv operating these as
fair-by-design instruments. That doesn't mean the v8 ruleset can't work
(it's a different, more specific rule set than what was tested there), but
it's the right prior to hold: `run_backtest.py` reports win rate against the
*real* payout-derived breakeven line (not 50%), splits results
chronologically into in-sample/out-of-sample, and flags whether any edge is
statistically significant — read the out-of-sample numbers, not the
in-sample ones, before deciding anything changes.

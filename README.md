# quantum-tick

Deriv synthetic-indices trading bot: a pluggable signal-engine framework
(v8's SMC-style ruleset, a Donchian breakout, and a random-baseline
control all implement one `Strategy` interface), a real-history backtesting
engine, and a live execution service — rebuilt on an N-tier architecture
from the original single-file `dt_bot_v8.py` (kept at
[legacy/dt_bot_v8.py](legacy/dt_bot_v8.py) for reference).

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
  domain/         Pure strategy logic — candles, filters, entries, targets.
                  No I/O, no logging, fully unit-tested (tests/).
    strategies/   Pluggable Strategy interface (base.py) + implementations:
                  V8Strategy, BreakoutStrategy, RandomStrategy. Add a new
                  strategy by adding one class here — the backtest engine
                  and CLI don't change.
  infrastructure/
    deriv/        REST auth (account bootstrap + OTP), async WebSocket
                  client (req_id-correlated request/response), paginated
                  historical-candle fetch.
  persistence/    SQLAlchemy models + repositories (candle cache, live
                  trades, backtest runs/trades). Session factory is
                  injected, never imported as a global.
  services/       SignalService (logging wrapper over domain/strategy),
                  LiveTradingService (the live scan/trade loop, v8-only).
  backtesting/    One bar-by-bar replay engine shared by every Strategy,
                  outcome scoring against real expiry prices, in-sample/
                  out-of-sample stats, position-sizing (flat vs. martingale)
                  simulation, reporting.
  research/       General-purpose stats (autocorrelation, runs test,
                  cross-series correlation) for edge-hunting, separate from
                  the live trading path.
  indicators.py   SMA/EMA/RSI/MACD (hand-verified), shared by domain
                  strategies and the xmlbots interpreter below.
  xmlbots/        Parser + IR + interpreter that turns a Deriv Bot (DBot)
                  Blockly XML export into the same Strategy interface as
                  everything else -- lets a real external bot collection be
                  mined and backtested like any in-house strategy. See
                  domain/strategies/xmlbot_strategy.py for the adapter.
scripts/          CLI entrypoints: diagnose_auth, fetch_history, run_backtest
                  (--strategy v8|breakout|random|all), run_live,
                  run_position_sizing_comparison, research_cross_symbol,
                  research_new_indices, xmlbots_scan_corpus, xmlbots_backtest.
tests/            Unit tests for the domain/backtesting/xmlbots layers.
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

# 3. Backtest a strategy against that cached history, in-sample/out-of-sample
python scripts/run_backtest.py --strategy v8        # or breakout, random, all

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

This project's research
([docs/research/RESEARCH_FINDINGS.md](docs/research/RESEARCH_FINDINGS.md))
now covers three strategies run through the same engine — v8's SMC-style
ruleset, a classic Donchian breakout, and a random coin-flip control —
plus cross-symbol lead-lag, day-of-week bias, and the original direction/
autocorrelation/runs-test battery. All converge on the same answer: no
exploitable directional edge found in R_10-R_100 Rise/Fall. v8 and
breakout's win rates are statistically indistinguishable from the random
baseline's, and Deriv's synthetic indices are, by their own stated design,
generated by an audited CSPRNG (cryptographically unpredictable, not just
empirically so — see RESEARCH_FINDINGS.md section 6). `run_backtest.py`
reports win rate against the *real* payout-derived breakeven line (not
50%), split chronologically into in-sample/out-of-sample with significance
testing and max-consecutive-loss tracking — read the out-of-sample numbers,
not the in-sample ones.

`scripts/run_position_sizing_comparison.py` compares flat-stake vs.
martingale sizing on real trade sequences: martingale does not fix a lack
of edge (bet sizing can't change win probability), and empirically would
have ruined a $1,000 account well before finishing the 60-day backtest
period on every symbol tested, from ordinary observed losing streaks.

35 more strategies were mined from a real external collection of 3,358
community-authored Deriv bots (ORSTAC) via `scripts/xmlbots_backtest.py` —
same answer: 0 of 140 out-of-sample (strategy, symbol) comparisons survived
Bonferroni correction with a positive edge (115 were significant, and every
one of those 115 was a *loss* — see RESEARCH_FINDINGS.md section 8).

If you pick this project back up looking for an edge, don't just keep
inventing rule variants against this same 60-day dataset — at 5%
significance, ~1 in 20 genuinely edge-less strategies will look
"significant" by chance alone, so open-ended searching eventually
manufactures a false positive. Genuinely untested avenues instead: the 658
tick-duration ORSTAC bots (needs real tick data, not built here), Step
Index / Jump Index (confirmed to offer Rise/Fall, unlike Range
Break/Boom/Crash — see RESEARCH_FINDINGS.md section 5), or a market with
real order-flow microstructure.

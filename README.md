# quantum-tick

[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-92%20passing-brightgreen?logo=pytest&logoColor=white)](tests/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Edge found](https://img.shields.io/badge/statistical%20edge-none%20found-critical)](docs/research/RESEARCH_FINDINGS.md)

A Deriv synthetic-indices trading bot rebuilt from a broken single-file
script into an N-tier Python project: a pluggable strategy framework, a
real-history backtesting engine with proper statistical rigor, and a live
execution service. Built around one question — does any Rise/Fall strategy
on Deriv's Volatility indices (R_10–R_100) have a real, out-of-sample edge?
— and answered it honestly across six independent lines of evidence.

> **Not financial advice, and not a profitable trading system.** This
> project's own research ([docs/research/RESEARCH_FINDINGS.md](docs/research/RESEARCH_FINDINGS.md))
> tested six independent strategy families — including 35 real strategies
> mined from a 3,358-bot community collection — against real historical
> data and found no statistically validated edge in any of them. It's
> shared as an engineering and research writeup, not a trading signal
> source. `DRY_RUN=true` by default; see [Safety](#safety).

## 🔌 Why this needed rebuilding, not just a config fix

Deriv now runs two API generations in parallel. The credentials this
project uses belong to the new "Options API" generation (alphanumeric
app_id + `pat_...` token), which requires a REST → OTP → WebSocket
handshake — not the legacy in-band `authorize` message the original
`dt_bot_v8.py` used. That mismatch, not a bad credential, is why it stopped
connecting. See [docs/postmortem/PROJECT_POSTMORTEM.md](docs/postmortem/PROJECT_POSTMORTEM.md)
items 2–8 for the full diagnosis and [scripts/diagnose_auth.py](scripts/diagnose_auth.py)
for a minimal script that proves the new flow end to end.

## 🏗️ Architecture

```
src/quantum_tick/
  config/         Settings (pydantic-settings, .env-backed)
  domain/         Pure strategy logic — candles, filters, entries, targets,
                  indicators (SMA/EMA/RSI/MACD). No I/O, no logging, fully
                  unit-tested (tests/).
    strategies/   Pluggable Strategy interface (base.py) + implementations:
                  V8Strategy, BreakoutStrategy, RandomStrategy, XmlBotStrategy.
                  Adding a new strategy means adding one class here — the
                  backtest engine and CLI don't change.
  infrastructure/
    deriv/        REST auth (account bootstrap + OTP), async WebSocket
                  client (req_id-correlated request/response), paginated
                  historical-candle fetch.
  persistence/    SQLAlchemy models + repositories (candle cache, live
                  trades, backtest runs). Session factory is injected,
                  never imported as a global.
  services/       Live scan/trade loop (v8 strategy only) and its logging.
  backtesting/    One bar-by-bar, no-lookahead replay engine shared by
                  every Strategy — outcome scoring against real expiry
                  prices, in-sample/out-of-sample stats, position-sizing
                  (flat vs. martingale) simulation, reporting.
  research/       General-purpose stats (autocorrelation, runs test,
                  cross-series correlation) for edge-hunting.
  xmlbots/        Parser + IR + interpreter that turns a Deriv Bot (DBot)
                  Blockly XML export into the same Strategy interface as
                  everything else, so a real external bot collection can
                  be mined and backtested like any in-house strategy.
scripts/          CLI entrypoints — see Usage below.
tests/            Unit tests for the domain/backtesting/xmlbots layers.
docs/postmortem/  Deriv API integration lessons from this project's history.
docs/research/    The full statistical research trail behind the
                  "not financial advice" disclaimer above.
legacy/           The original single-file bot, kept for reference.
```

## ⚙️ Setup

```bash
python -m venv .venv
./.venv/Scripts/python -m pip install -e ".[dev]"
cp .env.example .env   # fill in real values; .env is gitignored
```

## ▶️ Usage

```bash
# Prove the auth flow works in isolation (run this first if anything else fails)
python scripts/diagnose_auth.py

# Cache real historical candles for every symbol in .env's SYMBOLS
python scripts/fetch_history.py --days 60

# Backtest a strategy against that cached history, in-sample/out-of-sample
python scripts/run_backtest.py --strategy v8   # or breakout, random, all

# Compare flat-stake vs. martingale position sizing on a strategy's real trades
python scripts/run_position_sizing_comparison.py --strategy breakout

# Mine and backtest an external Deriv Bot (DBot) XML collection
python scripts/xmlbots_scan_corpus.py --corpus-dir <path>
python scripts/xmlbots_backtest.py --corpus-dir <path>

# Run the live bot (DRY_RUN=true by default — logs trades, places none)
python scripts/run_live.py

# Run the unit test suite
python -m pytest
```

## 🛡️ Safety

- `.env` holds real credentials and is gitignored; `.env.example` is the
  committed template.
- The live service only places real orders when **both** `DRY_RUN=false`
  and `DERIV_ACCOUNT_TYPE=real` — the default is a demo, dry-run account
  that logs what it would have traded.
- Daily loss cap and max-trades-per-day limits (`MAX_DAILY_LOSS`,
  `MAX_TRADES_PER_DAY` in `.env`) carry over from the original bot.

## 🔬 The research, summarized

Full writeup: [docs/research/RESEARCH_FINDINGS.md](docs/research/RESEARCH_FINDINGS.md).
Six independent tests, all converging on the same answer — **no
exploitable directional edge in R_10–R_100 Rise/Fall**:

1. **v8's SMC-style ruleset** (trend + BOS/CHoCH + entry patterns) — no
   significant out-of-sample edge on any symbol.
2. **Donchian channel breakout** (a structurally different rule, fixed
   parameters) — every symbol loses relative to breakeven.
3. **A random coin-flip baseline** — loses significantly against
   breakeven on every symbol, and is statistically indistinguishable from
   both strategies above.
4. **Cross-symbol correlation and day-of-week bias** — nothing survives
   correction; no effect either way.
5. **35 real strategies mined from 3,358 community-authored Deriv bots**
   (see `xmlbots/`) — 0 of 140 out-of-sample comparisons survived a
   Bonferroni correction with a positive edge.
6. **Why**: Deriv states these indices run on an audited CSPRNG —
   cryptographically unpredictable by design, not just empirically so —
   which an independent 15-million-tick external study also confirms.

Every backtest scores against the *real* payout-derived breakeven line
(not 50%), splits chronologically into in-sample/out-of-sample, and
reports significance and max-consecutive-loss — read the out-of-sample
numbers, not the in-sample ones. `run_position_sizing_comparison.py`
additionally shows martingale doesn't fix a lack of edge: simulated
against real trade sequences, it would have required a bet a $1,000
account couldn't cover within the first fifth of trades, on every symbol.

If you pick this project back up looking for an edge, resist the urge to
keep inventing rule variants against the same 60-day dataset — at 5%
significance, roughly 1 in 20 genuinely edge-less strategies will look
"significant" by chance alone, so open-ended searching eventually
manufactures a false positive rather than finding a real one. Genuinely
untested avenues: the 658 tick-duration ORSTAC bots (needs real tick data
and a parallel engine, not built here), Step Index / Jump Index (confirmed
to offer Rise/Fall, unlike Range Break/Boom-Crash), or a market with real
order-flow microstructure instead of an RNG.

# Research Findings: Searching for an Exploitable Edge on Deriv Synthetic Indices

This documents every hypothesis tested, the data behind each result, and why the
project stopped where it did. Kept as a permanent record so future work doesn't
re-run the same searches from scratch -- and so a future contributor doesn't
mistake "we haven't found an edge yet" for "we haven't looked."

## Background

The original plan (see `C:\Users\DT Wijesekara\.claude\plans\swirling-wondering-clock.md`)
translated 8 candlestick-pattern strategies from a Quotex-focused PDF into
precise rules and backtested them against real Deriv Volatility 75 Index
(`R_75`) history. All 8 failed: every strategy clustered at 47-51% win rate
against a 54.1% breakeven line, on samples of 300-12,000 signals each,
consistent in-sample and out-of-sample. That result is what triggered the
pivot documented here -- abandoning the PDF strategies entirely and searching
for a real, data-driven edge instead.

**Every finding below is measured against real Deriv data pulled live via this
project's own `deriv/historical.py` and `scripts/fetch_*.py`, not simulated or
assumed.**

## 1. Direction (Rise/Fall) on R_75

129,599 real 1-minute candles (90 days).

- **Autocorrelation of candle direction**, lags 1-10: all |values| < 0.005
  (significance threshold ~0.0056). No signal.
- **Runs test** (Wald-Wolfowitz, tests independence of consecutive
  directions): z = -0.38. Not remotely significant (need |z| > 1.96).
- **Streak continuation**: P(continue) after streaks of 1-7 same-direction
  candles: 49.6%-50.4% at every length. No momentum, no reversion.
- **Mean reversion after large moves** (body > 1-2.5x ATR14): P(reverse next)
  49.2%-51.4%. No signal (the one 33% outlier at 2.5x ATR had n=6 -- noise).
- **Same battery repeated at 5-min, 15-min, 1-hour aggregation**: same null
  pattern at every timeframe.
- **Hour-of-day bias**: 48.8%-51.3% green across all 24 hours. No session
  effect (unsurprising -- these trade 24/7 with no real market open/close).
- **What IS real**: autocorrelation of |return| (volatility magnitude) is
  ~+0.08 at every lag 1-10 -- genuine volatility clustering. Not usable for a
  direction-only Rise/Fall bet.

**Conclusion**: R_75's 1-minute candle direction is statistically
indistinguishable from independent coin flips, at every timeframe tested.

## 2. Digit contracts (Matches/Differs, Over/Under, Odd/Even) on R_75

43,189 real ticks (the ~24h Deriv actually retains at tick resolution).
`pip_size` confirmed live at 4 decimals (do not assume 2 -- the platform UI
truncates display precision, the contract settles on the full 4).

- **Last-digit distribution**: chi-square 2.83 (full), 4.19 / 8.37 (split
  halves) vs. critical value 16.9. Uniform.
- **Odd/Even**: z = +0.09, +0.45, -0.32 (full/first-half/second-half). Noise,
  sign flips between halves.
- **Digit-to-digit transition matrix** (10x10, P(next digit | current
  digit)): one cell borderline-elevated on the full dataset (chi2=16.08,
  just under the 16.9 threshold) did NOT replicate in a split-half check --
  weak in the first half (8.91), only appeared in the second half (18.61),
  while a different row showed the same pattern in reverse. With 10 rows x 2
  halves = 20 tests at 5% significance, ~1 false positive is expected by pure
  chance. That's what this was.

**Conclusion**: no exploitable digit bias on R_75.

## 3. Direction on other Volatility indices + Bull/Bear indices

30 days each, same %green / autocorrelation / runs-test battery:

| Symbol | %green | z (vs 50%) | runs z |
|---|---|---|---|
| R_10 | 50.02% | +0.10 | +0.98 |
| R_25 | 49.97% | -0.14 | -0.66 |
| R_50 | 50.28% | +1.18 | +0.44 |
| R_100 | 50.33% | +1.35 | +0.31 |
| RDBULL | 50.63% | +2.61 | +0.47 |
| RDBEAR | 49.40% | -2.49 | +0.00 |

RDBULL/RDBEAR are mildly elevated but weak (z~2.5), and with 8 symbols tested
at once, 1-2 borderline results are expected from multiple comparisons alone.
Nowhere near a real signal.

## 4. Boom/Crash indices -- a real bias that doesn't survive contact with the payoff

This is the one genuinely interesting finding, and the most important lesson
of this research phase.

**Candle-color frequency is massively skewed by design**: BOOM1000 candles
were 94.4% red / 5.6% green over 30 days (43,200 real candles); CRASH1000 was
the mirror (94.4% green). z-scores in the hundreds -- not remotely noise, this
is a deliberately engineered feature (steady drift one way, rare sharp spikes
the other).

**This is not tradeable via Rise/Fall.** Confirmed via a live `contracts_for`
call: BOOM1000 and CRASH1000 offer exactly two contract categories --
Accumulators (`ACCU`) and Multipliers (`MULTUP`/`MULTDOWN`) -- zero Rise/Fall
configurations. (`proposal` calls for `CALL`/`PUT` on these symbols return
`TradingDurationNotAllowed`.) This is very likely deliberate on Deriv's part,
precisely because the color bias would otherwise be trivially exploitable by a
contract that pays on color alone.

**Accumulators: negative EV**, calibrated against real tick-level volatility.
Deriv's own `proposal` response includes `ticks_stayed_in` -- empirical
historical survival data. Computed expected value (in stake multiples) for an
"always hold until breach" policy and for cash-out-at-tick-K policies, growth
rates 1% and 5%:
- growth=1%: EV ranges from -88% (hold to 250-tick cap) to -9.6% (cash out at
  5 ticks) -- every K tested is negative.
- growth=5%: mostly negative, one borderline positive result (+6.1% at K=20)
  from only 100 samples -- exactly the kind of single noisy number this
  project's own methodology says not to trust without much more data and
  out-of-sample validation.

**Multipliers: the color bias doesn't translate to price-level profit.**
This is the key insight, and it was only caught by simulating against
*actual* historical data instead of trusting the color-frequency stat:

```
CRASH1000, 30 real days, 43,199 candles:
  Green candles: 40,731 (94.4%)  mean +0.0059%  ->  sum +240.3%
  Red candles:    2,425 ( 5.6%)  mean -0.1009%  ->  sum -244.6%
  Net price change over 30 days: -2.79%
```

The rare red candles average ~17x the magnitude of the frequent green ones,
and the sums nearly cancel -- a "sawtooth" design where cumulative price
movement is roughly fair (slightly negative here) even though candle *count*
is wildly skewed. A simulated always-long Multiplier position (real candle
data, real confirmed stop-out mechanics: loss capped at 90% of stake, 0.6%
entry commission) **lost money at every leverage level tested (5x-500x), even
at 5x where zero stop-outs were triggered over the whole 30 days** -- because
the position simply rode the same -2.79% net drift the raw price data shows.

**Why this matters methodologically**: Rise/Fall pays on candle *color*.
Multipliers and Accumulators pay on *price level* / *tick-level stability*.
Checking only color frequency and generalizing to "this must be a profitable
bias" is exactly the "score against a proxy instead of what actually
determines payout" mistake this project's own postmortem warns about
(Checklist B item 6) -- caught here specifically *because* the available
contract types forced a check against the real payoff, not because it was
anticipated in advance.

## Overall conclusion (as of the original research phase)

No real, exploitable, out-of-sample-stable edge was found for:
- Rise/Fall direction on R_75, R_10, R_25, R_50, R_100, RDBULL, RDBEAR
- Digit contracts on R_75
- Multipliers or Accumulators on Boom/Crash indices

This is consistent with Deriv operating these as fair-by-design synthetic
instruments. Untested remaining avenues, noted for anyone picking this back
up: Step Index and Range Break indices (different generation mechanics, not
yet checked), and non-price-history approaches (execution-speed arbitrage,
cross-symbol correlation) -- neither pursued in this session per the project
owner's decision to stop here rather than keep searching without a new,
well-motivated hypothesis.

---

## 5. Follow-up session (quantum-tick project, 2026-08-16): four more independent tests, same conclusion

Picking up the untested avenues above, plus re-testing the actual v8
trading ruleset (not just raw direction statistics) against real data.
Reproducible via `scripts/run_backtest.py`, `scripts/run_backtest_breakout.py`,
`scripts/research_cross_symbol.py`, `scripts/run_position_sizing_comparison.py`.

**v8's full SMC-style ruleset** (trend + BOS/CHoCH + ENGULFING/HOP entries +
5 additional filters), no-lookahead bar-replay against 60 real days
(86,400 1-min candles) per symbol on R_10/25/50/75/100: no statistically
significant out-of-sample edge on any symbol (n=416-454 out-of-sample
trades/symbol). R_10 is significantly *losing* (out-of-sample edge -7.4%,
p=0.0026). Max consecutive losses observed: 8-13 per symbol.

**Step Index / Jump Index do offer Rise/Fall** (CALL/PUT) -- corrects an
earlier bug in this session where `contracts_for` was called with an
invalid `currency` field (see PROJECT_POSTMORTEM item 6) and every result
silently came back "unavailable". Range Break and Boom/Crash confirmed to
NOT offer Rise/Fall (MULTUP/MULTDOWN/ACCU only), consistent with section 4
above. Step/Jump were not further tested this session (project owner chose
to stay focused on R_10-R_100 for now) -- a real, still-open avenue for
whoever picks this up next.

**Cross-symbol lead-lag**: Pearson correlation between every pair of
{R_10,R_25,R_50,R_75,R_100} at lags -5..+5 minutes, aligned by shared
candle epoch (110 pair/lag combinations, Bonferroni-corrected threshold
p<0.000455). Zero combinations survived correction. No evidence these
series lead/lag each other, consistent with independently-generated RNGs.

**Day-of-week bias**: never checked in the original research (only
hour-of-day was). All 7 days x 5 symbols land in 49.5%-50.8% green, with
n~11,000-13,000 candles per bucket -- pure noise, no effect (unsurprising:
these trade 24/7 with no real weekly session structure).

**Donchian channel breakout** -- a genuinely different strategy family
from v8 (classic 20-period channel breakout, fixed parameters chosen
before running, not tuned to this data): a much larger, cleaner sample
(~2,400 out-of-sample trades/symbol vs. v8's ~430) shows **every symbol
losing relative to breakeven in both in-sample and out-of-sample splits**,
3 of 5 significantly so (R_10, R_75, R_100). Win rates cluster tightly at
48-51%, i.e. close to a fair coin -- exactly what's expected if direction
truly can't be predicted from price history: an entry rule can only choose
*which* fair coin-flips to take, not make the coin unfair, so it converges
to the fair-coin rate minus the house edge built into the payout ratio.

**Martingale position sizing does not fix a lack of edge, and is
dangerous in practice.** Simulated flat-stake ($1) vs. classic martingale
(x2 after each loss, reset on win) over the breakout strategy's real trade
sequences: with a hypothetical $1,000 bankroll, martingale required a
single bet the account couldn't cover ("ruin") within the first 21%-39% of
trades on **every symbol** (peak required stake ~$1,024, i.e. 2^10 x the
$1 base, from an ordinary observed 10-loss streak). Final P&L under
martingale was also worse than flat-stake on 3 of 5 symbols; the two that
looked "better" only did because the simulation was cut short at ruin, not
because martingale actually outperformed.

### Updated overall conclusion

Two structurally different strategy families (SMC pattern-based, and
classic channel breakout), cross-symbol correlation, day-of-week, and the
original direction/autocorrelation/runs-test battery all agree: **no
exploitable directional edge in R_10-R_100 Rise/Fall has been found**, and
results consistently cluster at/below the fair-coin rate, below the real
breakeven line. This is the expected signature of a genuinely fair,
RNG-driven instrument with a house edge in the payout structure, not a
strategy-design problem waiting to be solved with a cleverer rule.

Continuing to invent and test more rule variants against this same 60-day
dataset would not be a neutral next step -- at a 5% significance threshold,
roughly 1 in 20 genuinely edge-less strategies will appear "significant" by
chance alone, so open-ended searching eventually manufactures a false
positive rather than finding a real one. Genuinely open avenues, if this is
picked up again: Step/Jump indices (confirmed Rise/Fall-eligible, not yet
tested), a real market with actual order-flow microstructure (forex/crypto
via a different broker/API) where technical patterns have a real
theoretical basis, or accepting there's no edge here and running the
existing bot as a demo/paper-trading exercise rather than a search for one.

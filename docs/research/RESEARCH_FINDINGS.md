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
Reproducible via `scripts/run_backtest.py --strategy v8|breakout`,
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

## 6. Why: Deriv's synthetic indices are cryptographically-generated by design, not just empirically unpredictable

Before testing yet another rule, it's worth understanding *why* every test
above lands the same way. Deriv states its synthetic indices are generated
by Cryptographically Secure Pseudo-Random Number Generators (CSPRNGs) --
the same class of algorithm used in banking and blockchain -- seeded and
then audited by independent third parties (RNG auditors such as iTech Labs
evaluate exactly this: statistical randomness, internal state,
unpredictability, non-repeatability). Deriv's own explanation
([experts.deriv.com](https://experts.deriv.com/insights/do-brokers-manipulate-synthetic-indices))
states the feed is a single central algorithm broadcast identically to all
clients, blind to individual account/position data.

This matters methodologically: a CSPRNG's defining property is that its
future output is computationally infeasible to predict even given complete
knowledge of every past output (unlike a naive PRNG, which can sometimes be
reverse-engineered from enough samples). If Deriv's stated design is
accurate, "no pattern found" isn't just an empirical result that a cleverer
rule might overturn -- it's the expected outcome by construction, the same
way no amount of chart-pattern analysis lets you predict the next output of
`/dev/urandom`.

**Independent external corroboration**: a separate analysis of 15.2M real
Deriv ticks (Boom 1000 / Crash 1000, Jan-Apr 2026 -- different data, symbols,
and specific hypotheses than either this project or the original research
phase) used a pre-registered methodology with "kill gates" specifically to
prevent post-hoc goalpost-moving, and reached the same conclusion: the spike
process is memoryless (Poisson-like, no lag-1 autocorrelation), post-spike
drift showed no advantage over random windows across 16 comparisons, and
even a hypothetical edge would be smaller than the round-trip spread. ([I
Analyzed 15 Million Ticks of Deriv Synthetic Data. The Edge Did Not Survive
The Costs. -- Oheneba Berko, Medium](https://medium.com/@shiekwaku100/i-analyzed-15-million-ticks-of-deriv-synthetic-data-the-edge-did-not-survive-the-costs-5e1e85481c4d))

## 7. The cleanest test yet: a random-baseline strategy beats v8 and breakout at being average

To make the comparison rigorous rather than qualitative, the backtester was
generalized into a pluggable `Strategy` interface (`domain/strategies/`) so
v8, the Donchian breakout, and a pure coin-flip strategy all run through the
identical no-lookahead engine and get scored identically. The coin-flip
strategy (`RandomStrategy`, seeded for reproducibility) fires a 50/50
CALL/PUT on every eligible candle -- no market logic at all.

Because it fires far more often (~28,800 signals/symbol vs. v8's ~1,400 and
breakout's ~8,100), it has by far the most statistical power of any test in
this project:

| Strategy | Out-of-sample win rate range | Breakeven | Significant loss? |
|---|---|---|---|
| v8 | 44.7%-54.6% | 52.1% | R_10 only |
| Donchian breakout | 48.2%-51.1% | 52.1% | 3 of 5 symbols |
| **Random (coin flip)** | **49.8%-51.0%** | **52.1%** | **all 5 symbols, p<0.05 every time** |

The random baseline's win rate is statistically indistinguishable from
v8's and breakout's -- all three cluster at essentially the fair-coin rate,
below the payout-derived breakeven line. That's the clearest possible
demonstration that neither v8's multi-filter SMC-style rules nor a classic
channel breakout are doing anything a coin flip doesn't already do; the
consistent negative edge in all three is just the house edge built into the
payout ratio, showing up with enough samples to be statistically obvious
(random's out-of-sample n~8,640/symbol makes even a -1.1% edge significant).

Reproducible via `python scripts/run_backtest.py --strategy all`.

## 8. Mining 3,358 real community bots (ORSTAC corpus): same answer, from strategies we didn't design

A separate collection (github.com/alanvito1/ORSTAC, "4,000+ open-source
Deriv bots" scraped from trading Telegram/Facebook communities, mostly
Vietnamese/Portuguese-authored) was mined for genuinely independent
strategy ideas rather than more hypotheses invented in-house. Built:
`src/quantum_tick/xmlbots/` -- a Blockly-XML parser + IR + interpreter that
turns a Deriv Bot (DBot) export into the same `Strategy` interface v8/
breakout/random already use, plus `domain/indicators.py` (SMA/EMA/RSI/MACD,
hand-verified, the only indicator vocabulary actually present in the
corpus -- no Bollinger/Stochastic/ADX despite one bot's own marketing
description claiming Bollinger logic).

**The repo's own "curated" claims don't hold up.** Its `champions/`
folder markets 3 "elite, forensically-audited" bots; one of them
(`Rise-Fall - Consistent - Trends.xml`, described as "the master of
survival") turned out to have **no entry logic at all** -- it unconditionally
buys CALL every time, wrapped in a gentle martingale-like stake
progression. The repo also carries Deriv/BingX referral links throughout,
consistent with it being partly an affiliate funnel -- a reason to verify
everything independently rather than trust any in-repo performance claims,
which is what the rest of this section does.

**Corpus filtering**: of 3,358 bots, 981 are Rise/Fall on R_10-R_100.
Two-thirds (658) trade on tick-based duration/indicators -- out of scope
for this candle-based backtester (a tick-duration contract resolves in
seconds, faster than 1-minute candle data can honestly score; flagged as a
genuinely open follow-on, not silently approximated). Of the time-based
remainder, the parser fully resolved **160 bots -> 35 distinct strategies**
after deduping near-identical copies (community collections are mostly a
handful of real ideas re-shared under many filenames with cosmetic stake
differences -- one dedup group alone had 26 near-duplicate files).
Real, encountered parser gaps along the way (fixed): duration specified
directly on the market block instead of a separate `tradeOptions` block;
purchase decisions made by an if *nested inside* another if's branch
(needed a recursive decision-tree IR, not a flat one -- this alone
doubled the usable corpus); indicators computed into a named variable and
referenced later rather than inlined. Remaining unsupported constructs
(custom Blockly procedures, `Last Result`-dependent logic, a few other
block types) are real, documented scope boundaries, not silent
approximations.

**Result**: all 35 distinct strategies backtested against all 5 symbols,
same no-lookahead engine, same real payout-derived breakeven line, same
in-sample/out-of-sample split as every other strategy in this project.
140 (strategy, symbol) pairs produced a scoreable out-of-sample sample.
Of those:
- 115 were "significant" at the raw, *uncorrected* p<0.05 level -- and
  **every single one of the 115 was a significant loss**, not a win (the
  same large-sample house-edge signature the random baseline already
  demonstrated in section 7).
- Only 8 of 140 showed any positive edge at all, and none were significant
  even before correction.
- With a Bonferroni threshold sized to the actual 140 comparisons
  (p<0.000357), **zero survived** with a positive edge.

Reproducible via `python scripts/xmlbots_scan_corpus.py` (corpus
statistics) and `python scripts/xmlbots_backtest.py` (full backtest).

### Updated overall conclusion

Two structurally different in-house strategy families (SMC pattern-based,
classic channel breakout), a random coin-flip control, cross-symbol
correlation, day-of-week, the original direction/autocorrelation/runs-test
battery, **and 35 independently-authored real community strategies mined
from 3,358 candidates** all agree: **no exploitable directional edge in
R_10-R_100 Rise/Fall has been found**, and results consistently cluster
at/below the fair-coin rate -- statistically indistinguishable from the
random baseline -- below the real breakeven line. Section 6 explains *why*:
this is the expected signature of a CSPRNG-driven instrument by
cryptographic design, corroborated by an independent 15M-tick external
analysis, not a strategy-design problem waiting to be solved with a
cleverer rule -- and now also not a problem solvable by borrowing someone
else's rule instead of inventing one.

Continuing to invent and test more rule variants against this same 60-day
dataset would not be a neutral next step -- at a 5% significance threshold,
roughly 1 in 20 genuinely edge-less strategies will appear "significant" by
chance alone, so open-ended searching eventually manufactures a false
positive rather than finding a real one. Genuinely open avenues, if this is
picked up again: the 658 tick-based ORSTAC bots (needs real tick-level data
and a parallel tick-duration engine, not built here), Step/Jump indices
(confirmed Rise/Fall-eligible, not yet tested), a real market with actual
order-flow microstructure (forex/crypto via a different broker/API) where
technical patterns have a real theoretical basis, or accepting there's no
edge here and running the existing bot as a demo/paper-trading exercise
rather than a search for one.

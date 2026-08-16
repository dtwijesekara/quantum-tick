"""
================================================================
   DT Wijesekara Strategy Bot  v8
================================================================

v8 CHANGES vs v7  (based on 100-trade analysis):

PROBLEM 1 — ONE_COLOR entry was 100% of all trades
  One-Color is "last candle matches trend color" which is
  almost always true during a trend. It's too loose as an
  entry signal — it fires constantly.
  FIX: ONE_COLOR is now a TREND FILTER only (3+ same-color).
       Entry signal MUST be ENGULFING or HOP.

PROBLEM 2 — Post-impulse pullback entries (Screenshots 1 & 2)
  After a large body candle (>2.5x avg), price often retraces.
  Bot was entering INTO the retrace candle.
  FIX: post_impulse_filter() — if the candle BEFORE the signal
       candle has body > 2.5x avg = skip, likely retrace next.

PROBLEM 3 — Late / mid-candle entries (all 3 screenshots)
  Bot scans every 10 seconds and places at current tick price.
  The forming candle (candles[-1]) may have already moved far.
  FIX: late_entry_filter() — if candles[-1] has already moved
       > 1.5x avg body from its open = entry is too late, skip.

PROBLEM 4 — Extended move / exhaustion entries (Screenshot 3)
  5-6 same-color candles in a row = move is tired, not fresh.
  FIX: detect_trend() now returns None if 6+ consecutive candles
       of same color (exhaustion = no fresh setup available).

PROBLEM 5 — Same candle re-firing
  Bot scans every 10s. Could fire twice on the same candle if
  scan 1 finds signal but order is delayed.
  FIX: track last_signal_open_time per symbol. If candles[-2]
       open time matches last fired = skip.

ENTRY RULES (strict, v8):
  MUST have ALL of:
    ✅ Trend:     3–5 same-color candles (NOT 6+, that's exhaustion)
    ✅ Structure: BOS or CHoCH
    ✅ Entry:     ENGULFING or HOP (not one-color alone)
    ✅ Market:    Not choppy (v7 detector, retained)
  SKIP if ANY:
    ❌ Large FVG near price
    ❌ Previous candle was oversized impulse (post_impulse)
    ❌ Current forming candle already moved too far (late_entry)
    ❌ 6+ consecutive same-color candles (exhaustion)
    ❌ Same signal candle already fired for this symbol

AIMING LEVEL & DURATION LOGIC:
  Target = nearest swing high (bullish) or swing low (bearish).
  Duration = distance_to_target / avg_candle_body (in minutes).
  Clamped to 1–15 minutes.
  Why: if avg candle body = 5 points and target is 15 points
  away, expect ~3 candles = 3 minutes.
  In this system, most targets are 1–3 candles away = 1–3 min.
  A target 10+ candles away is unlikely to be reached in time
  → the 15-minute cap prevents over-optimistic durations.
================================================================
"""

import asyncio
import websockets
import json
import logging
import sys
from datetime import datetime

# ─── ENABLE ANSI COLORS ON WINDOWS ────────────────────────────────────────────
if sys.platform == "win32":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass

# ─── ANSI COLOR CODES ─────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"

# ─── CUSTOM CONSOLE FORMATTER ─────────────────────────────────────────────────
class CleanFormatter(logging.Formatter):
    def format(self, record):
        ts = self.formatTime(record, "%H:%M:%S")
        if record.levelno >= logging.ERROR:
            return f"{RED}{ts}  [ERR]  {record.getMessage()}{RESET}"
        if record.levelno >= logging.WARNING:
            return f"{YELLOW}{ts}  [WARN] {record.getMessage()}{RESET}"
        return f"{ts}  {record.getMessage()}"

_file_handler = logging.FileHandler("dt_bot_v8.log", encoding="utf-8")
_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

_console = logging.StreamHandler(sys.stdout)
try:
    _console.stream.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
_console.setFormatter(CleanFormatter())

log = logging.getLogger("dt_bot")
log.setLevel(logging.INFO)
log.addHandler(_file_handler)
log.addHandler(_console)
log.propagate = False

def green(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{GREEN}{ts}  {msg}{RESET}", flush=True)
    with open("dt_bot_v8.log", "a", encoding="utf-8") as f:
        f.write(f"{ts}  {msg}\n")


# ─── CONFIG ───────────────────────────────────────────────────────────────────
# Kept for reference only -- this legacy in-band auth flow no longer works
# against current Deriv credentials; see README.md and
# docs/postmortem/PROJECT_POSTMORTEM.md. Original token redacted (already
# rotated/dead) before this file was made public.
API_TOKEN  = 'REDACTED_ROTATED_TOKEN'
APP_ID     = 1089
SYMBOLS    = ['R_10', 'R_25', 'R_50', 'R_75', 'R_100']
TIMEFRAME  = 60      # 1-minute candles
STAKE      = 1.00
CURRENCY   = "USD"

MAX_DAILY_LOSS  = 10.00
MAX_TRADES_DAY  = 10
session_pnl     = 0.0
trades_today    = 0

# Strategy params
TREND_MIN_CANDLES    = 3    # minimum same-color candles for trend
TREND_MAX_CANDLES    = 5    # if MORE than this = exhaustion = skip  (v8)
BOS_LOOKBACK         = 15
SWING_LOOKBACK       = 20
SWING_STRENGTH       = 2
AVG_BODY_LOOKBACK    = 5
MIN_DURATION_MINS    = 1
MAX_DURATION_MINS    = 15
LARGE_FVG_BODY_MULT  = 2.0

# Entry technique params
HOP_MIN_BODY_MULT    = 0.10   # min gap for HOP = 10% of avg body
ENGULF_COVERAGE      = 0.70   # engulfing must cover 70% of prev candle

# v8 new filters
POST_IMPULSE_MULT    = 2.5    # prev candle > 2.5x avg = impulse = skip
LATE_ENTRY_MULT      = 1.5    # forming candle > 1.5x avg from open = too late

# Choppy market params (from v7)
CHOP_LOOKBACK         = 8
CHOP_ALTER_THRESHOLD  = 0.60
CHOP_BODY_THRESHOLD   = 0.70
CHOP_DIR_THRESHOLD    = 0.62

# Session counters
technique_counts  = {"ENGULFING": 0, "HOP": 0}
skip_counts       = {
    "trend": 0, "structure": 0, "choppy": 0,
    "fvg": 0, "no_entry": 0, "post_impulse": 0,
    "late_entry": 0, "exhaustion": 0, "same_candle": 0
}

# Per-symbol: track the open-time of last candle we fired on
last_signal_open: dict = {}


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def color(c):
    return "GREEN" if c['close'] > c['open'] else "RED"

def body(c):
    return abs(c['close'] - c['open'])

def avg_body_size(candles):
    bodies = [body(c) for c in candles[-(AVG_BODY_LOOKBACK + 1):-1] if body(c) > 0]
    return (sum(bodies) / len(bodies)) if bodies else 0.0001


# ══════════════════════════════════════════════════════════════════════════════
#  FILTER 1 — TREND  (3–5 consecutive same-color, not 6+)
#
#  Why 5 max: after 6+ candles the move is "extended/exhausted".
#  Screenshot 3 shows a 5-candle red cascade — entry at bottom = loss.
#  A fresh setup needs a SHORT, clean directional run, not an exhausted one.
# ══════════════════════════════════════════════════════════════════════════════
def detect_trend(candles):
    closed = candles[-(TREND_MAX_CANDLES + 4):-1]
    colors = [color(c) for c in closed]

    # Count consecutive same-color from most recent backward
    last_color = colors[-1]
    run = 0
    for c in reversed(colors):
        if c == last_color:
            run += 1
        else:
            break

    if run > TREND_MAX_CANDLES:
        # Exhaustion: too many same-color in a row
        return None, "exhaustion"

    if run >= TREND_MIN_CANDLES:
        trend = "BULLISH" if last_color == "GREEN" else "BEARISH"
        return trend, None

    return None, "no_trend"


# ══════════════════════════════════════════════════════════════════════════════
#  FILTER 2 — BOS / CHoCH
# ══════════════════════════════════════════════════════════════════════════════
def detect_bos_choch(candles, trend):
    window  = candles[-(BOS_LOOKBACK + 2):-2]
    current = candles[-2]
    if len(window) < 4:
        return None

    swing_high = max(c['high'] for c in window)
    swing_low  = min(c['low']  for c in window)
    prior      = [color(c) for c in window[:len(window) // 2]]

    if trend == "BULLISH" and current['close'] > swing_high:
        had_bear = prior.count("RED") > prior.count("GREEN")
        return 'CHoCH' if had_bear else 'BOS'

    if trend == "BEARISH" and current['close'] < swing_low:
        had_bull = prior.count("GREEN") > prior.count("RED")
        return 'CHoCH' if had_bull else 'BOS'

    return None


# ══════════════════════════════════════════════════════════════════════════════
#  FILTER 3 — CHOPPY MARKET  (from v7)
# ══════════════════════════════════════════════════════════════════════════════
def is_choppy_market(candles, trend):
    window = candles[-(CHOP_LOOKBACK + 2):-1]
    if len(window) < CHOP_LOOKBACK:
        return False, ""

    signals_fired = []
    colors = [color(c) for c in window]

    alternations = sum(1 for i in range(len(colors) - 1) if colors[i] != colors[i+1])
    alter_rate = alternations / (len(colors) - 1)
    if alter_rate > CHOP_ALTER_THRESHOLD:
        signals_fired.append(f"alternation={alter_rate:.0%}")

    recent_bodies   = [body(c) for c in window[-4:] if body(c) > 0]
    baseline_bodies = [body(c) for c in window      if body(c) > 0]
    if recent_bodies and baseline_bodies:
        ratio = (sum(recent_bodies)/len(recent_bodies)) / (sum(baseline_bodies)/len(baseline_bodies))
        if ratio < CHOP_BODY_THRESHOLD:
            signals_fired.append(f"body_shrink={ratio:.0%}")

    trend_color = "GREEN" if trend == "BULLISH" else "RED"
    consistency = sum(1 for c in colors if c == trend_color) / len(colors)
    if consistency < CHOP_DIR_THRESHOLD:
        signals_fired.append(f"dir={consistency:.0%}")

    is_chop = len(signals_fired) >= 2
    return is_chop, " | ".join(signals_fired)


# ══════════════════════════════════════════════════════════════════════════════
#  FILTER 4 — LARGE FVG
# ══════════════════════════════════════════════════════════════════════════════
def has_large_fvg(candles, trend):
    avg   = avg_body_size(candles)
    limit = avg * LARGE_FVG_BODY_MULT
    for i in range(-8, -3):
        c1 = candles[i]
        c3 = candles[i + 2]
        if trend == "BULLISH":
            if (c3['open'] - c1['high']) > limit:
                return True
        elif trend == "BEARISH":
            if (c1['low'] - c3['open']) > limit:
                return True
    return False


# ══════════════════════════════════════════════════════════════════════════════
#  FILTER 5 — POST-IMPULSE  (v8 NEW)
#
#  Checks if the candle BEFORE the signal candle was an oversized impulse.
#  If candles[-3] body > 2.5x avg: the market just made a big single-candle
#  move. The signal candle (candles[-2]) is the REACTION to that impulse.
#  Reaction candles often retrace — entering on them leads to losses.
#
#  Screenshot 1: big GREEN impulse → RED reaction → bot entered PUT on reaction
#  Screenshot 2: big RED impulse → tiny doji reaction → bot entered PUT on doji
#
#  candles[-3] = impulse candle (the one before signal)
#  candles[-2] = signal candle (what we're evaluating)
#  candles[-1] = current forming candle (where we'd enter)
# ══════════════════════════════════════════════════════════════════════════════
def has_post_impulse(candles):
    avg        = avg_body_size(candles)
    pre_signal = candles[-3]   # candle before the signal candle
    if body(pre_signal) > avg * POST_IMPULSE_MULT:
        ratio = body(pre_signal) / avg
        return True, f"prev_body={ratio:.1f}x_avg"
    return False, ""


# ══════════════════════════════════════════════════════════════════════════════
#  FILTER 6 — LATE ENTRY  (v8 NEW)
#
#  After a valid signal on candles[-2], we enter at the OPEN of candles[-1].
#  But the scan runs every 10 seconds. By the time we trade, candles[-1]
#  may have already moved significantly from its open.
#
#  If the forming candle has already moved > 1.5x avg body in the trade
#  direction, we are entering mid-candle — the "easy money" is already gone.
#
#  Example (bullish): candles[-1] open=100, current_tick=103, avg_body=1.5
#  Movement = 3.0 = 2x avg body → LATE, skip
#
#  candles[-1]['open']  = open of the FORMING candle
#  candles[-1]['close'] = current tick price (real-time, still forming)
# ══════════════════════════════════════════════════════════════════════════════
def is_late_entry(candles, trend):
    avg     = avg_body_size(candles)
    forming = candles[-1]
    limit   = avg * LATE_ENTRY_MULT

    if trend == "BULLISH":
        move = forming['close'] - forming['open']
    else:
        move = forming['open'] - forming['close']

    if move > limit:
        pct = move / avg
        return True, f"forming_moved={pct:.1f}x_avg"
    return False, ""


# ══════════════════════════════════════════════════════════════════════════════
#  FILTER 7 — SAME CANDLE LOCK  (v8 NEW)
#
#  Prevents firing twice on the same signal candle.
#  Each symbol stores the 'open' time of the last candle we traded on.
#  If it matches candles[-2]['open'], skip — already fired this candle.
# ══════════════════════════════════════════════════════════════════════════════
def is_same_candle(symbol, candles):
    signal_candle_open = candles[-2].get('open_time', candles[-2].get('epoch', 0))
    if last_signal_open.get(symbol) == signal_candle_open:
        return True
    return False

def mark_candle_fired(symbol, candles):
    signal_candle_open = candles[-2].get('open_time', candles[-2].get('epoch', 0))
    last_signal_open[symbol] = signal_candle_open


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY TECHNIQUES  (v8: ENGULFING and HOP only)
#
#  ONE_COLOR is REMOVED as an entry technique.
#  It was 100% of all v7 trades and too weak as a signal.
#  It still exists implicitly in the trend filter (3+ same-color candles).
#
#  ENGULFING: current candle engulfs the previous opposite-color candle
#    - Requires: prev is opposite color, curr body covers ≥70% of prev body
#    - This is a REVERSAL or CONTINUATION pattern with real commitment
#
#  HOP (Hidden Open Point): candle opens with a gap vs previous close
#    - Bullish HOP: current candle opens BELOW previous close (gap down on buy)
#    - Bearish HOP: current candle opens ABOVE previous close (gap up on sell)
#    - The gap shows liquidity imbalance — strong directional intent
# ══════════════════════════════════════════════════════════════════════════════
def detect_entry(candles, trend):
    entries = []
    curr = candles[-2]   # signal candle (closed)
    prev = candles[-3]   # candle before signal
    avg  = avg_body_size(candles)

    curr_color = color(curr)
    prev_color = color(prev)
    curr_body_ = body(curr)
    prev_body_ = body(prev)

    # ── ENGULFING ─────────────────────────────────────────────────────────────
    if prev_body_ > 0:
        if trend == "BULLISH" and prev_color == "RED" and curr_color == "GREEN":
            cov = (curr['close'] - min(prev['open'], prev['close'])) / prev_body_
            if cov >= ENGULF_COVERAGE and curr_body_ >= prev_body_ * 0.7:
                entries.append("ENGULFING")
        elif trend == "BEARISH" and prev_color == "GREEN" and curr_color == "RED":
            cov = (max(prev['open'], prev['close']) - curr['close']) / prev_body_
            if cov >= ENGULF_COVERAGE and curr_body_ >= prev_body_ * 0.7:
                entries.append("ENGULFING")

    # ── HOP (Hidden Open Point) ───────────────────────────────────────────────
    min_gap = avg * HOP_MIN_BODY_MULT
    if trend == "BULLISH":
        # Buy HOP: current candle opens BELOW prev close (gap down = unfilled demand)
        gap = prev['close'] - curr['open']
        if gap >= min_gap and curr_color == "GREEN":
            entries.append("HOP")
    elif trend == "BEARISH":
        # Sell HOP: current candle opens ABOVE prev close (gap up = unfilled supply)
        gap = curr['open'] - prev['close']
        if gap >= min_gap and curr_color == "RED":
            entries.append("HOP")

    return entries


# ══════════════════════════════════════════════════════════════════════════════
#  TARGET (AIM LEVEL) & DURATION
#
#  AIM LEVEL: nearest swing high (bullish) or swing low (bearish)
#    within the last SWING_LOOKBACK candles.
#    Rationale: we're targeting the nearest point of prior price memory,
#    which price tends to revisit as liquidity sits there.
#
#  DURATION: distance_to_target / avg_candle_body = expected candles needed
#    Converted to minutes (each candle = 1 minute at TIMEFRAME=60s).
#    Clamped to 1–15 min.
#
#  In this system typical targets are 1–4 candles away,
#  so most durations will naturally fall to 1–4 minutes.
# ══════════════════════════════════════════════════════════════════════════════
def find_nearest_swing(candles, trend):
    s      = SWING_STRENGTH
    closed = candles[-(SWING_LOOKBACK + s + 2):-1]
    price  = candles[-2]['close']

    nearest_price    = None
    nearest_distance = float('inf')

    for i in range(s, len(closed) - s):
        c = closed[i]
        if trend == "BULLISH":
            ok = (all(c['high'] >= closed[i-j]['high'] for j in range(1, s+1)) and
                  all(c['high'] >= closed[i+j]['high'] for j in range(1, s+1)))
            if ok and c['high'] > price:
                d = c['high'] - price
                if d < nearest_distance:
                    nearest_distance = d
                    nearest_price    = c['high']
        else:
            ok = (all(c['low'] <= closed[i-j]['low'] for j in range(1, s+1)) and
                  all(c['low'] <= closed[i+j]['low'] for j in range(1, s+1)))
            if ok and c['low'] < price:
                d = price - c['low']
                if d < nearest_distance:
                    nearest_distance = d
                    nearest_price    = c['low']

    if nearest_price is None:
        recent = candles[-SWING_LOOKBACK:-1]
        if trend == "BULLISH":
            nearest_price = max(c['high'] for c in recent)
        else:
            nearest_price = min(c['low'] for c in recent)
        nearest_distance = abs(nearest_price - price)

    return nearest_price, nearest_distance


def estimate_duration(candles, distance):
    avg = avg_body_size(candles)
    raw = distance / avg if avg > 0 else MIN_DURATION_MINS
    return int(max(MIN_DURATION_MINS, min(MAX_DURATION_MINS, round(raw + 0.5))))


# ══════════════════════════════════════════════════════════════════════════════
#  MASTER SIGNAL ENGINE  (all 7 filters in order)
# ══════════════════════════════════════════════════════════════════════════════
def evaluate_signal(candles, symbol):
    needed = BOS_LOOKBACK + SWING_LOOKBACK + SWING_STRENGTH + CHOP_LOOKBACK + 8
    if len(candles) < needed:
        return None

    price = candles[-2]['close']

    # 1 — Trend (3–5 candles, not exhaustion)
    trend, reason = detect_trend(candles)
    if not trend:
        skip_counts["exhaustion" if reason == "exhaustion" else "trend"] += 1
        tag = "EXHAUSTED" if reason == "exhaustion" else "no_trend"
        recent = [color(c) for c in candles[-6:-1]]
        log.info(f"  [{symbol}] SKIP {tag:<14} {recent}")
        return None
    log.info(f"  [{symbol}] OK   trend={trend} price={price:.4f}")

    # 2 — Structure
    structure = detect_bos_choch(candles, trend)
    if not structure:
        skip_counts["structure"] += 1
        log.info(f"  [{symbol}] SKIP structure      no BOS/CHoCH")
        return None
    log.info(f"  [{symbol}] OK   structure={structure}")

    # 3 — Choppy market
    is_chop, chop_reason = is_choppy_market(candles, trend)
    if is_chop:
        skip_counts["choppy"] += 1
        log.info(f"  [{symbol}] SKIP choppy         {chop_reason}")
        return None

    # 4 — Large FVG
    if has_large_fvg(candles, trend):
        skip_counts["fvg"] += 1
        log.info(f"  [{symbol}] SKIP large_fvg      gap>{LARGE_FVG_BODY_MULT}x avg")
        return None

    # 5 — Post-impulse filter  (v8 NEW)
    is_impulse, impulse_reason = has_post_impulse(candles)
    if is_impulse:
        skip_counts["post_impulse"] += 1
        log.info(f"  [{symbol}] SKIP post_impulse   {impulse_reason}")
        return None

    # 6 — Entry technique (ENGULFING or HOP required)
    entries = detect_entry(candles, trend)
    if not entries:
        skip_counts["no_entry"] += 1
        log.info(f"  [{symbol}] SKIP no_entry       need ENGULFING or HOP")
        return None
    log.info(f"  [{symbol}] OK   entry={entries}")

    # 7 — Late entry filter  (v8 NEW)
    is_late, late_reason = is_late_entry(candles, trend)
    if is_late:
        skip_counts["late_entry"] += 1
        log.info(f"  [{symbol}] SKIP late_entry     {late_reason}")
        return None

    # 8 — Same candle lock  (v8 NEW)
    if is_same_candle(symbol, candles):
        skip_counts["same_candle"] += 1
        log.info(f"  [{symbol}] SKIP same_candle    already fired this candle")
        return None

    # All filters passed
    target, distance = find_nearest_swing(candles, trend)
    duration         = estimate_duration(candles, distance)
    avg              = avg_body_size(candles)
    log.info(f"  [{symbol}] OK   target={target:.4f} dist={distance:.4f} avg={avg:.4f} => {duration}min")

    return {
        "symbol":        symbol,
        "contract_type": "CALL" if trend == "BULLISH" else "PUT",
        "trend":         trend,
        "structure":     structure,
        "entries":       entries,
        "target":        target,
        "distance":      distance,
        "avg_body":      avg,
        "duration_mins": duration,
        "price":         price,
        "candles":       candles,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  EXECUTE TRADE
# ══════════════════════════════════════════════════════════════════════════════
async def execute_trade(websocket, signal):
    global trades_today, session_pnl

    for t in signal['entries']:
        if t in technique_counts:
            technique_counts[t] += 1

    mark_candle_fired(signal['symbol'], signal['candles'])

    tech = " + ".join(signal['entries'])
    sep  = "=" * 57

    green(sep)
    green(f"  TRADE #{trades_today + 1}  [{signal['symbol']}] {signal['contract_type']}")
    green(f"  Trend      : {signal['trend']}  |  Structure : {signal['structure']}")
    green(f"  Technique  : {tech}")
    green(f"  Entry price: {signal['price']:.4f}")
    green(f"  Target     : {signal['target']:.4f}  ({signal['distance']:.4f} away)")
    green(f"  Avg body   : {signal['avg_body']:.4f}  =>  Duration: {signal['duration_mins']} min")

    await websocket.send(json.dumps({
        "proposal":      1,
        "amount":        STAKE,
        "basis":         "stake",
        "contract_type": signal['contract_type'],
        "currency":      CURRENCY,
        "duration":      signal['duration_mins'],
        "duration_unit": "m",
        "symbol":        signal['symbol'],
    }))
    prop = json.loads(await websocket.recv())

    if 'error' in prop:
        log.error(f"Proposal error: {prop['error']['message']}")
        green(sep)
        return False

    payout = prop['proposal']['payout']
    pid    = prop['proposal']['id']
    green(f"  Payout     : ${payout:.2f}  |  Stake: ${STAKE:.2f}")

    await websocket.send(json.dumps({"buy": pid, "price": STAKE}))
    buy = json.loads(await websocket.recv())

    if 'error' in buy:
        log.error(f"Buy error: {buy['error']['message']}")
        green(sep)
        return False

    trades_today += 1
    tx = buy['buy']['transaction_id']
    green(f"  [PLACED]   TX: {tx}")
    green(f"  Trades     : {trades_today}/{MAX_TRADES_DAY}  |  Session P&L: ${session_pnl:.2f}")
    green(sep)
    return True


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN LOOP
# ══════════════════════════════════════════════════════════════════════════════
async def run_bot():
    uri = f"wss://ws.binaryws.com/websockets/v3?app_id={APP_ID}"

    while True:
        try:
            async with websockets.connect(uri) as websocket:
                log.info("Connected to Deriv")
                await websocket.send(json.dumps({"authorize": API_TOKEN}))
                auth = json.loads(await websocket.recv())
                if 'error' in auth:
                    log.error(f"Auth failed: {auth['error']['message']}")
                    return

                bal = auth['authorize']['balance']
                log.info(f"Balance: {bal} {CURRENCY}")
                log.info("─" * 57)
                log.info("  DT Wijesekara v8  |  Minute contracts")
                log.info("  Entry   : ENGULFING or HOP only (ONE_COLOR removed)")
                log.info("  Filters : trend(3-5) + BOS/CHoCH + no FVG + not choppy")
                log.info("  v8 NEW  : post-impulse + late-entry + exhaustion + same-candle lock")
                log.info("─" * 57)

                candle_count = BOS_LOOKBACK + SWING_LOOKBACK + SWING_STRENGTH + CHOP_LOOKBACK + 14

                while True:
                    if session_pnl <= -MAX_DAILY_LOSS:
                        log.warning(f"Daily loss limit reached. Stopping.")
                        _print_session_summary()
                        return
                    if trades_today >= MAX_TRADES_DAY:
                        log.warning(f"Max {MAX_TRADES_DAY} trades reached.")
                        _print_session_summary()
                        return

                    trade_executed = False
                    last_signal    = None

                    for symbol in SYMBOLS:
                        if trade_executed:
                            break

                        await websocket.send(json.dumps({
                            "ticks_history": symbol,
                            "end":           "latest",
                            "count":         candle_count,
                            "style":         "candles",
                            "granularity":   TIMEFRAME
                        }))
                        res = json.loads(await websocket.recv())

                        if 'candles' not in res:
                            await asyncio.sleep(1)
                            continue

                        signal = evaluate_signal(res['candles'], symbol)
                        if signal:
                            last_signal = signal
                            success = await execute_trade(websocket, signal)
                            if success:
                                trade_executed = True

                        await asyncio.sleep(1)

                    if trade_executed and last_signal:
                        wait = last_signal['duration_mins'] * 60 + 15
                        log.info(f"  Waiting {wait}s ({last_signal['duration_mins']}min + buffer)...")
                        await asyncio.sleep(wait)
                    else:
                        t = datetime.now().strftime('%H:%M:%S')
                        log.info(f"  [{t}] No setup — next scan in 10s")
                        await asyncio.sleep(10)

        except websockets.exceptions.ConnectionClosedError:
            log.warning("Connection dropped. Reconnecting in 5s...")
            await asyncio.sleep(5)
        except Exception as e:
            log.error(f"Error: {e}")
            await asyncio.sleep(5)


def _print_session_summary():
    log.info("─" * 57)
    log.info(f"  SESSION SUMMARY")
    log.info(f"  Trades placed : {trades_today}")
    log.info(f"  Techniques    : {technique_counts}")
    log.info(f"  Skip reasons  : {skip_counts}")
    log.info("─" * 57)


if __name__ == "__main__":
    asyncio.run(run_bot())

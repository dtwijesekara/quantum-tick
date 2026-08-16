import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def candle(open_, high, low, close, epoch):
    """Explicit OHLC helper -- every caller states `open_` so a candle's
    bullish/bearish classification is never left to accident (see
    docs/postmortem/PROJECT_POSTMORTEM.md item 13)."""
    return {"open": open_, "high": high, "low": low, "close": close, "epoch": epoch}


def green(base_epoch, i, open_=100.0, size=1.0):
    o = open_
    return candle(o, o + size, o - 0.1, o + size, base_epoch + i * 60)


def red(base_epoch, i, open_=100.0, size=1.0):
    o = open_
    return candle(o, o + 0.1, o - size, o - size, base_epoch + i * 60)

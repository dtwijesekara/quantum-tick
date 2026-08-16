"""Evaluates a parsed BotDefinition's entry logic against a live candle
window. Kept separate from parser.py: the parser turns XML into IR once,
the interpreter runs that IR every replay step (called once per candle
during backtesting, so this stays allocation-light).

Raises RequiresTickData for any bot whose indicator input is raw ticks
(TicksSeries) -- this backtest phase only has candle-close data cached, and
approximating a tick-based indicator with candle closes would silently
misrepresent what the bot actually does (see docs/research/xmlbots.md for
why tick-based bots are a separate, not-yet-built phase).
"""

from __future__ import annotations

from quantum_tick.domain.candles import is_green
from quantum_tick.domain.indicators import ema, macd, rsi, sma
from quantum_tick.xmlbots.ir import (
    BoolExpr,
    BotDefinition,
    CandleField,
    Compare,
    Condition,
    EntryLogic,
    Expr,
    IfBranch,
    IndicatorCall,
    IsCandleBlack,
    LogicOp,
    Number,
    NoAction,
    Purchase,
    TicksSeries,
    TickValue,
)


class RequiresTickData(Exception):
    pass


def evaluate_entry_logic(bot: BotDefinition, candles: list[dict]) -> Purchase | None:
    return _evaluate_node(bot.entry_logic, candles)


def _evaluate_node(node, candles: list[dict]) -> Purchase | None:
    """`node` is a Purchase, NoAction, or (nested) EntryLogic."""
    if isinstance(node, Purchase):
        return node
    if isinstance(node, NoAction):
        return None

    entry_logic: EntryLogic = node
    for branch in entry_logic.branches:
        if _evaluate_condition(branch.condition, candles):
            return _evaluate_node(branch.action, candles)
    return _evaluate_node(entry_logic.default, candles)


def _evaluate_condition(condition: Condition, candles: list[dict]) -> bool:
    if isinstance(condition, Compare):
        left = _evaluate_expr(condition.left, candles)
        right = _evaluate_expr(condition.right, candles)
        if left is None or right is None:
            return False  # not enough history yet for an indicator -> condition can't fire
        return _compare(condition.op, left, right)

    if isinstance(condition, LogicOp):
        results = [_evaluate_condition(op, candles) for op in condition.operands]
        return all(results) if condition.op == "AND" else any(results)

    if isinstance(condition, BoolExpr):
        value = _evaluate_expr(condition.expr, candles)
        return bool(value)

    raise TypeError(f"unhandled condition type: {type(condition)}")


def _compare(op: str, left: float, right: float) -> bool:
    if op == "GT":
        return left > right
    if op == "LT":
        return left < right
    if op == "GTE":
        return left >= right
    if op == "LTE":
        return left <= right
    if op == "EQ":
        return left == right
    if op == "NEQ":
        return left != right
    raise ValueError(f"unhandled compare op: {op}")


def _evaluate_expr(expr: Expr, candles: list[dict]) -> float | None:
    if isinstance(expr, Number):
        return expr.value

    if isinstance(expr, TickValue):
        # last fully-closed price at decision time -- candles[-1] is the
        # entry/forming candle and must not influence the decision (see
        # backtesting/engine.py's no-lookahead discipline).
        return candles[-2]["close"]

    if isinstance(expr, IsCandleBlack):
        return 0.0 if is_green(candles[-2]) else 1.0

    if isinstance(expr, CandleField):
        # standalone use (e.g. "close > SMA(close,20)"), not as an
        # indicator's input source -- last fully-closed candle, same
        # no-lookahead rule as TickValue above.
        return candles[-2][expr.field]

    if isinstance(expr, IndicatorCall):
        series = _resolve_series(expr.input_source, candles)
        if expr.name == "sma":
            return sma(series, expr.params["period"])
        if expr.name == "ema":
            return ema(series, expr.params["period"])
        if expr.name == "rsi":
            return rsi(series, expr.params["period"])
        if expr.name in ("macd_line", "macd_signal"):
            result = macd(series, expr.params["fast"], expr.params["slow"], expr.params["signal"])
            if result is None:
                return None
            macd_line, signal_line, _ = result
            return macd_line if expr.name == "macd_line" else signal_line
        raise ValueError(f"unhandled indicator: {expr.name}")

    raise TypeError(f"unhandled expression type: {type(expr)}")


def _resolve_series(source, candles: list[dict]) -> list[float]:
    if isinstance(source, TicksSeries):
        raise RequiresTickData("indicator input is raw ticks, not candle closes")
    if isinstance(source, CandleField):
        # exclude candles[-1] (the still-forming entry candle) -- only
        # fully-closed candles may feed a decision.
        closed = candles[:-1]
        return [c[source.field] for c in closed]
    raise TypeError(f"unhandled input source type: {type(source)}")


def bot_requires_tick_data(bot: BotDefinition) -> bool:
    """Static check (no candle data needed) so unsupported-for-this-phase
    bots can be filtered out before backtesting even starts."""

    def expr_needs_ticks(expr: Expr) -> bool:
        if isinstance(expr, IndicatorCall):
            return isinstance(expr.input_source, TicksSeries)
        return False

    def cond_needs_ticks(condition: Condition) -> bool:
        if isinstance(condition, Compare):
            return expr_needs_ticks(condition.left) or expr_needs_ticks(condition.right)
        if isinstance(condition, LogicOp):
            return any(cond_needs_ticks(op) for op in condition.operands)
        if isinstance(condition, BoolExpr):
            return expr_needs_ticks(condition.expr)
        return False

    def node_needs_ticks(node) -> bool:
        if isinstance(node, EntryLogic):
            return any(cond_needs_ticks(b.condition) or node_needs_ticks(b.action) for b in node.branches) or \
                node_needs_ticks(node.default)
        return False  # Purchase / NoAction

    return node_needs_ticks(bot.entry_logic)

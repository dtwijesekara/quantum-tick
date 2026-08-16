from __future__ import annotations

from quantum_tick.domain.strategies.base import DetectedSignal
from quantum_tick.xmlbots.interpreter import evaluate_entry_logic
from quantum_tick.xmlbots.ir import BotDefinition, Compare, EntryLogic, Expr, IndicatorCall, LogicOp

_DURATION_TO_MINS = {"s": 1 / 60, "m": 1, "h": 60}
_MIN_WINDOW = 30


def _max_period(bot: BotDefinition) -> int:
    """Largest lookback any indicator in this bot's entry logic needs, so
    `required_window` is sized per-bot instead of a fixed guess that could
    silently under-detect a bot using e.g. SMA(200)."""

    def expr_period(expr: Expr) -> int:
        if isinstance(expr, IndicatorCall):
            p = expr.params
            return max(p.get("period", 0), p.get("slow", 0) + p.get("signal", 0))
        return 0

    def node_period(node) -> int:
        if not isinstance(node, EntryLogic):
            return 0
        best = node_period(node.default)
        for branch in node.branches:
            best = max(best, _condition_period(branch.condition, expr_period), node_period(branch.action))
        return best

    return node_period(bot.entry_logic)


def _condition_period(condition, expr_period) -> int:
    if isinstance(condition, Compare):
        return max(expr_period(condition.left), expr_period(condition.right))
    if isinstance(condition, LogicOp):
        return max((_condition_period(op, expr_period) for op in condition.operands), default=0)
    return 0


class XmlBotStrategy:
    """Adapter over a parsed ORSTAC XML bot's entry logic (xmlbots/ir.py +
    interpreter.py).

    Bots specifying duration in seconds are floored to 1 minute -- the
    finest granularity this backtest's candle cache has, and the closest
    honest approximation without tick-level data.
    """

    def __init__(self, bot: BotDefinition):
        self.bot = bot
        self.name = f"xmlbot:{bot.source_path}"
        self.required_window = max(_MIN_WINDOW, _max_period(bot) + 10)
        self.duration_mins = max(1, round(bot.duration_value * _DURATION_TO_MINS[bot.duration_unit]))

    def detect(self, candles: list[dict], symbol: str) -> DetectedSignal | None:
        purchase = evaluate_entry_logic(self.bot, candles)
        if purchase is None:
            return None
        return DetectedSignal(contract_type=purchase.contract_type, duration_mins=self.duration_mins, technique="xmlbot")

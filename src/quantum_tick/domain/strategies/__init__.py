from quantum_tick.domain.strategies.base import DetectedSignal, Strategy
from quantum_tick.domain.strategies.breakout_strategy import BreakoutStrategy
from quantum_tick.domain.strategies.random_strategy import RandomStrategy
from quantum_tick.domain.strategies.v8_strategy import V8Strategy

STRATEGY_REGISTRY = {
    "v8": V8Strategy,
    "breakout": BreakoutStrategy,
    "random": RandomStrategy,
}

__all__ = [
    "DetectedSignal",
    "Strategy",
    "V8Strategy",
    "BreakoutStrategy",
    "RandomStrategy",
    "STRATEGY_REGISTRY",
]

"""Parses a Deriv Bot (DBot/Blockly) XML file into ir.BotDefinition.

Conservative by design: any block type, field, or shape not in the
observed ORSTAC vocabulary makes the whole bot `supported=False` with a
reason, rather than guessing at what an unrecognized block means. A wrong
guess would silently corrupt a backtest; a skipped bot just shrinks the
sample.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from quantum_tick.xmlbots.ir import (
    BotDefinition,
    BoolExpr,
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

NS = "{http://www.w3.org/1999/xhtml}"


class UnsupportedBot(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def parse_file(path: str) -> BotDefinition:
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        return BotDefinition(
            source_path=path, symbol="", trade_type="", market="",
            candle_interval=0, duration_unit="", duration_value=0,
            entry_logic=EntryLogic(branches=(), default=NoAction()),
            supported=False, unsupported_reason=f"xml parse error: {exc}",
        )

    root = tree.getroot()
    try:
        symbol, trade_type, market, candle_interval = _find_trade_definition(root)
        duration_unit, duration_value = _find_duration(root)
        variables = _build_variable_table(root)
        entry_logic = _find_entry_logic(root, variables)
    except UnsupportedBot as exc:
        return BotDefinition(
            source_path=path, symbol="", trade_type="", market="",
            candle_interval=0, duration_unit="", duration_value=0,
            entry_logic=EntryLogic(branches=(), default=NoAction()),
            supported=False, unsupported_reason=exc.reason,
        )
    except Exception as exc:  # noqa: BLE001 - ~1000 files of messy real-world XML;
        # one unanticipated shape must not crash the whole corpus scan.
        return BotDefinition(
            source_path=path, symbol="", trade_type="", market="",
            candle_interval=0, duration_unit="", duration_value=0,
            entry_logic=EntryLogic(branches=(), default=NoAction()),
            supported=False, unsupported_reason=f"unexpected parser error: {type(exc).__name__}: {exc}",
        )

    return BotDefinition(
        source_path=path, symbol=symbol, trade_type=trade_type, market=market,
        candle_interval=candle_interval, duration_unit=duration_unit, duration_value=duration_value,
        entry_logic=entry_logic, supported=True,
    )


# ---- trade / market / duration -------------------------------------------


def _field_text(block: ET.Element, name: str) -> str | None:
    el = block.find(f"{NS}field[@name='{name}']")
    return el.text if el is not None else None


def _find_trade_definition(root: ET.Element) -> tuple[str, str, str, int]:
    for block in root.iter(f"{NS}block"):
        if block.get("type") not in ("trade", "market"):
            continue
        symbol = _field_text(block, "SYMBOL_LIST")
        trade_type = _field_text(block, "TRADETYPE_LIST")
        market = _field_text(block, "MARKET_LIST")
        interval = _field_text(block, "CANDLEINTERVAL_LIST")
        if symbol and trade_type:
            return symbol, trade_type, market or "", int(interval) if interval and interval.isdigit() else 60
    raise UnsupportedBot("no trade/market definition block found")


def _find_duration(root: ET.Element) -> tuple[str, int]:
    # Duration is specified either via a separate `tradeOptions` block, or
    # directly as fields/values on the `trade`/`market` block itself --
    # both shapes appear in the corpus.
    for block in root.iter(f"{NS}block"):
        if block.get("type") not in ("tradeOptions", "trade", "market"):
            continue
        unit = _field_text(block, "DURATIONTYPE_LIST")
        dur_value_el = block.find(f"{NS}value[@name='DURATION']")
        value = None
        if dur_value_el is not None:
            # a real block (user-set) takes priority over a shadow (default)
            num_block = dur_value_el.find(f"{NS}block[@type='math_number']")
            if num_block is None:
                num_block = dur_value_el.find(f"{NS}shadow[@type='math_number']")
            if num_block is not None:
                num_field = num_block.find(f"{NS}field[@name='NUM']")
                if num_field is not None and num_field.text is not None:
                    value = float(num_field.text)
        if unit and value is not None:
            return unit, int(value)
    raise UnsupportedBot("no resolvable duration found")


# ---- variable table --------------------------------------------------------
#
# Many bots compute an indicator once ("set RSI = rsi(close, 14)") and
# reference the named variable in conditions afterward, rather than inlining
# the indicator call. So the table maps name -> Expr (a literal Number OR an
# IndicatorCall/TickValue/etc.), built in document order so a variable's own
# definition can reference earlier variables. A variable whose definition
# itself can't be parsed (procedure call, unsupported block, forward
# reference) is simply left out of the table -- any condition that then
# references it correctly reports "unresolvable variable reference" rather
# than guessing.


def _build_variable_table(root: ET.Element) -> dict[str, Expr]:
    table: dict[str, Expr] = {}
    for block in root.iter(f"{NS}block"):
        if block.get("type") != "variables_set":
            continue
        var_field = block.find(f"{NS}field[@name='VAR']")
        value_el = block.find(f"{NS}value[@name='VALUE']")
        if var_field is None or var_field.text is None or value_el is None:
            continue
        if var_field.text in table:
            continue  # first assignment wins (typical single-init pattern)
        value_block = value_el.find(f"{NS}block")
        if value_block is None:
            continue
        try:
            table[var_field.text] = _parse_expr(value_block, table)
        except UnsupportedBot:
            pass  # leave unresolved; a later reference will report it
    return table


# ---- entry logic (before_purchase) -----------------------------------------


def _find_entry_logic(root: ET.Element, variables: dict[str, Expr]) -> EntryLogic:
    bp = None
    for block in root.iter(f"{NS}block"):
        if block.get("type") == "before_purchase":
            bp = block
            break
    if bp is None:
        raise UnsupportedBot("no before_purchase block")

    stack = bp.find(f"{NS}statement[@name='BEFOREPURCHASE_STACK']")
    if stack is None:
        raise UnsupportedBot("before_purchase has no BEFOREPURCHASE_STACK")

    top = stack.find(f"{NS}block")
    if top is None:
        raise UnsupportedBot("before_purchase stack is empty")

    # `_parse_action` already walks the whole chain (skipping `variables_set`,
    # `notify`, etc.) looking for a `purchase` or `controls_if` -- covers
    # both "starts with controls_if" and "some setup blocks, then
    # controls_if" and "no condition at all, just an unconditional
    # purchase" in one pass.
    action = _parse_action(stack, variables)
    if isinstance(action, EntryLogic):
        return action
    if isinstance(action, Purchase):
        # Unconditional entry logic: some bots always buy the same side
        # with no condition at all (a real, if trivial, hypothesis worth
        # backtesting on its own merits -- not the same claim as their
        # money-management description, which is handled separately).
        return EntryLogic(branches=(), default=action)

    raise UnsupportedBot(f"before_purchase stack has no purchase or controls_if anywhere (starts with {top.get('type')})")


def _parse_controls_if(block: ET.Element, variables: dict[str, Expr]) -> EntryLogic:
    mutation = block.find(f"{NS}mutation")
    n_elseif = int(mutation.get("elseif", "0")) if mutation is not None else 0
    has_else = bool(mutation is not None and mutation.get("else") == "1")

    branches = []
    for i in range(n_elseif + 1):
        cond_el = block.find(f"{NS}value[@name='IF{i}']")
        do_el = block.find(f"{NS}statement[@name='DO{i}']")
        if cond_el is None:
            raise UnsupportedBot(f"controls_if missing IF{i}")
        condition = _parse_condition(_first_block(cond_el), variables)
        action = _parse_action(do_el, variables) if do_el is not None else NoAction()
        branches.append(IfBranch(condition=condition, action=action))

    default: "Purchase | NoAction | EntryLogic"
    if has_else:
        else_el = block.find(f"{NS}statement[@name='ELSE']")
        default = _parse_action(else_el, variables) if else_el is not None else NoAction()
    else:
        default = NoAction()

    return EntryLogic(branches=tuple(branches), default=default)


def _first_block(container: ET.Element | None) -> ET.Element:
    if container is None:
        raise UnsupportedBot("expected a value/statement slot, found none")
    el = container.find(f"{NS}block")
    if el is None:
        raise UnsupportedBot("expected a <block> child, found none")
    return el


def _parse_action(statement_el: ET.Element, variables: dict[str, Expr]) -> "Purchase | NoAction | EntryLogic":
    """Walk the DO/ELSE statement's block chain looking for a `purchase`
    block or a nested `controls_if` -- the decision may not be the first
    block (often preceded by `notify`, `variables_set`, etc.)."""
    block = statement_el.find(f"{NS}block")
    seen = 0
    while block is not None and seen < 50:  # guard against malformed cyclic XML
        if block.get("type") == "purchase":
            purchase_type = _field_text(block, "PURCHASE_LIST")
            if purchase_type not in ("CALL", "PUT"):
                raise UnsupportedBot(f"unsupported PURCHASE_LIST value: {purchase_type}")
            return Purchase(contract_type=purchase_type)
        if block.get("type") == "controls_if":
            return _parse_controls_if(block, variables)
        next_el = block.find(f"{NS}next")
        block = next_el.find(f"{NS}block") if next_el is not None else None
        seen += 1
    return NoAction()


def _parse_condition(block: ET.Element, variables: dict[str, Expr]) -> Condition:
    block_type = block.get("type")

    if block_type == "logic_operation":
        op = _field_text(block, "OP")
        if op not in ("AND", "OR"):
            raise UnsupportedBot(f"unsupported logic_operation OP: {op}")
        a = _parse_condition(_first_block(block.find(f"{NS}value[@name='A']")), variables)
        b = _parse_condition(_first_block(block.find(f"{NS}value[@name='B']")), variables)
        return LogicOp(op=op, operands=(a, b))

    if block_type == "logic_compare":
        op = _field_text(block, "OP")
        if op not in ("GT", "LT", "GTE", "LTE", "EQ", "NEQ"):
            raise UnsupportedBot(f"unsupported logic_compare OP: {op}")
        left = _parse_expr(_first_block(block.find(f"{NS}value[@name='A']")), variables)
        right = _parse_expr(_first_block(block.find(f"{NS}value[@name='B']")), variables)
        return Compare(op=op, left=left, right=right)

    if block_type == "is_candle_black":
        return BoolExpr(IsCandleBlack())

    raise UnsupportedBot(f"unsupported condition block type: {block_type}")


def _parse_expr(block: ET.Element, variables: dict[str, Expr]) -> Expr:
    block_type = block.get("type")

    if block_type == "math_number":
        num = _field_text(block, "NUM")
        if num is None:
            raise UnsupportedBot("math_number missing NUM field")
        return Number(float(num))

    if block_type == "variables_get":
        var_field = block.find(f"{NS}field[@name='VAR']")
        name = var_field.text if var_field is not None else None
        if name is None or name not in variables:
            raise UnsupportedBot(f"unresolvable variable reference: {name}")
        return variables[name]

    if block_type == "tick":
        return TickValue()

    if block_type in ("ohlc_values", "get_ohlc", "read_ohlc"):
        # a raw candle field used directly as a comparable value (e.g.
        # "close > SMA(close, 20)"), not as an indicator's input source.
        return _parse_input_source(block)

    if block_type in ("sma", "ema", "rsi"):
        input_el = block.find(f"{NS}value[@name='INPUT']")
        period_el = block.find(f"{NS}value[@name='PERIOD']")
        source = _parse_input_source(_first_block(input_el)) if input_el is not None else TicksSeries()
        period = _resolve_number(period_el, variables) if period_el is not None else None
        if period is None:
            raise UnsupportedBot(f"{block_type} block missing a resolvable PERIOD")
        return IndicatorCall(name=block_type, input_source=source, params={"period": int(period)})

    if block_type == "macda":
        fields_val = _field_text(block, "MACDFIELDS_LIST")
        if fields_val == "1":
            name = "macd_line"
        elif fields_val == "2":
            name = "macd_signal"
        else:
            raise UnsupportedBot(f"unsupported MACDFIELDS_LIST value: {fields_val}")

        input_el = block.find(f"{NS}value[@name='INPUT']")
        source = _parse_input_source(_first_block(input_el)) if input_el is not None else TicksSeries()

        fast = _resolve_number(block.find(f"{NS}value[@name='FAST_EMA_PERIOD']"), variables)
        slow = _resolve_number(block.find(f"{NS}value[@name='SLOW_EMA_PERIOD']"), variables)
        signal = _resolve_number(block.find(f"{NS}value[@name='SMA_PERIOD']"), variables)
        if fast is None or slow is None or signal is None:
            raise UnsupportedBot("macda block missing resolvable fast/slow/signal periods")
        return IndicatorCall(
            name=name, input_source=source,
            params={"fast": int(fast), "slow": int(slow), "signal": int(signal)},
        )

    raise UnsupportedBot(f"unsupported expression block type: {block_type}")


def _parse_input_source(block: ET.Element):
    block_type = block.get("type")
    if block_type == "ticks":
        return TicksSeries()
    if block_type in ("ohlc_values", "get_ohlc", "read_ohlc"):
        field_el = block.find(f"{NS}field[@name='OHLCFIELD_LIST']")
        field_name = field_el.text if field_el is not None else "close"
        return CandleField(field=field_name or "close")
    raise UnsupportedBot(f"unsupported indicator input source: {block_type}")


def _resolve_number(value_el: ET.Element | None, variables: dict[str, Expr]) -> float | None:
    """A DURATION/PERIOD value slot may hold a real user block, or fall
    back to a <shadow> default if the user never customized it -- a real
    block takes priority."""
    if value_el is None:
        return None
    block = value_el.find(f"{NS}block")
    if block is None:
        block = value_el.find(f"{NS}shadow")
    if block is None:
        return None
    if block.get("type") == "math_number":
        num = _field_text(block, "NUM")
        return float(num) if num is not None else None
    if block.get("type") == "variables_get":
        var_field = block.find(f"{NS}field[@name='VAR']")
        name = var_field.text if var_field is not None else None
        resolved = variables.get(name) if name else None
        return resolved.value if isinstance(resolved, Number) else None
    return None

async def get_symbol_specification(
    self,
    symbol: str,
) -> dict:
    """
    Return broker-provided trading specifications for a symbol.

    This is read-only.
    No order is placed or modified.
    """

    if not symbol:
        raise ValueError(
            "symbol is required"
        )

    if mt5 is None:
        raise MT5ServiceError(
            "MetaTrader5 package is not available"
        )

    def _get_specification():
        selected = mt5.symbol_select(
            symbol,
            True,
        )

        if not selected:
            raise MT5ServiceError(
                f"Unable to select symbol: {symbol}"
            )

        info = mt5.symbol_info(symbol)

        if info is None:
            error = mt5.last_error()

            raise MT5ServiceError(
                f"Unable to retrieve symbol info "
                f"for {symbol}: {error}"
            )

        return info._asdict()

    data = await asyncio.to_thread(
        _get_specification
    )

    return {
        "symbol": data.get(
            "name",
            symbol,
        ),
        "digits": data.get(
            "digits"
        ),
        "point": data.get(
            "point"
        ),
        "spread": data.get(
            "spread"
        ),
        "spread_float": data.get(
            "spread_float"
        ),
        "tick_size": data.get(
            "trade_tick_size"
        ),
        "tick_value": data.get(
            "trade_tick_value"
        ),
        "tick_value_profit": data.get(
            "trade_tick_value_profit"
        ),
        "tick_value_loss": data.get(
            "trade_tick_value_loss"
        ),
        "contract_size": data.get(
            "trade_contract_size"
        ),
        "volume_min": data.get(
            "volume_min"
        ),
        "volume_max": data.get(
            "volume_max"
        ),
        "volume_step": data.get(
            "volume_step"
        ),
        "volume_limit": data.get(
            "volume_limit"
        ),
        "trade_mode": data.get(
            "trade_mode"
        ),
        "trade_execution_mode": data.get(
            "trade_exemode"
        ),
        "trade_stops_level": data.get(
            "trade_stops_level"
        ),
        "trade_freeze_level": data.get(
            "trade_freeze_level"
        ),
        "currency_base": data.get(
            "currency_base"
        ),
        "currency_profit": data.get(
            "currency_profit"
        ),
        "currency_margin": data.get(
            "currency_margin"
        ),
    }

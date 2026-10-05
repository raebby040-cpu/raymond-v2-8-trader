@staticmethod
def mark_partial_close(
    db: Session,
    position_id: str,
    remaining_quantity: float,
    *,
    execution_price: float,
    closed_quantity: Optional[float] = None,
) -> Optional[Position]:
    """
    Persist a paper partial-close event.

    IMPORTANT ACCOUNTING RULE:

        partial_close_pnl is CUMULATIVE.

    Therefore:

        total_trade_pnl =
            cumulative partial-close PnL
            +
            final remaining-position PnL

    This avoids losing earlier partial-close profits/losses.

    PAPER ONLY.
    No broker order is created.
    """

    position = PositionRepository.get_by_position_id(
        db,
        position_id,
    )

    if position is None:
        return None

    if position.status != PositionStatus.OPEN:
        return position

    remaining = float(remaining_quantity)
    price = float(execution_price)

    if remaining < 0:
        raise ValueError(
            "remaining_quantity cannot be negative"
        )

    if price <= 0:
        raise ValueError(
            "execution_price must be greater than zero"
        )

    current_quantity = float(
        position.remaining_quantity
        if position.remaining_quantity is not None
        else position.quantity
    )

    if closed_quantity is None:
        closed = current_quantity - remaining
    else:
        closed = float(closed_quantity)

    if closed <= 0:
        raise ValueError(
            "closed_quantity must be greater than zero"
        )

    if closed > current_quantity + 1e-12:
        raise ValueError(
            "closed_quantity cannot exceed current remaining quantity"
        )

    expected_remaining = (
        current_quantity - closed
    )

    if abs(
        expected_remaining - remaining
    ) > 1e-9:
        raise ValueError(
            "remaining_quantity and closed_quantity are inconsistent"
        )

    direction = PositionRepository._direction_value(
        position.direction
    )

    entry_price = float(
        position.entry_price
    )

    if direction == TradeDirection.BUY.value:
        price_move = (
            price - entry_price
        )

    elif direction == TradeDirection.SELL.value:
        price_move = (
            entry_price - price
        )

    else:
        raise ValueError(
            f"Unsupported position direction: {position.direction}"
        )

    contract_size = PositionRepository._contract_size(
        position.symbol
    )

    realized_partial_pnl = (
        price_move
        * closed
        * contract_size
    )

    # --------------------------------------------------------
    # CUMULATIVE PARTIAL-CLOSE PNL
    # --------------------------------------------------------

    previous_partial_pnl = float(
        position.partial_close_pnl or 0.0
    )

    cumulative_partial_pnl = (
        previous_partial_pnl
        + realized_partial_pnl
    )

    # --------------------------------------------------------
    # REMAINING POSITION
    # --------------------------------------------------------

    position.remaining_quantity = remaining
    position.quantity = remaining

    # --------------------------------------------------------
    # PARTIAL-CLOSE ACCOUNTING
    # --------------------------------------------------------

    position.partial_close_applied = 1

    # These two fields describe the MOST RECENT partial close.
    position.partial_close_price = price
    position.partial_close_quantity = closed

    # This field is now explicitly cumulative.
    position.partial_close_pnl = (
        cumulative_partial_pnl
    )

    position.management_status = "reduced"

    position.last_management_action = (
        "PARTIAL_CLOSE"
    )

    position.last_management_time = (
        datetime.utcnow()
    )

    try:
        db.commit()
        db.refresh(position)

        return position

    except Exception:
        db.rollback()
        raise

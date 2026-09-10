from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional


class EmergencyStopError(RuntimeError):
    """Raised when emergency-stop state cannot be used safely."""


@dataclass(frozen=True)
class SafetyConfig:
    """
    Configuration for emergency-stop and connection-loss protection.

    The system fails closed: if connection health cannot be established,
    new trading must not be allowed.
    """

    heartbeat_timeout_seconds: float = 15.0
    require_healthy_connection: bool = True


@dataclass(frozen=True)
class SafetyStatus:
    """Current global trading safety state."""

    trading_allowed: bool
    emergency_stop_active: bool
    connection_healthy: bool
    connection_stale: bool
    reason: str
    last_heartbeat: Optional[datetime]


class EmergencyStopManager:
    """
    Safety gate for the trading system.

    This class does not place, modify, or close broker orders.

    It only determines whether the system is currently allowed to
    proceed toward a trading operation.
    """

    def __init__(
        self,
        config: Optional[SafetyConfig] = None,
    ) -> None:
        self.config = config or SafetyConfig()

        if self.config.heartbeat_timeout_seconds <= 0:
            raise EmergencyStopError(
                "heartbeat_timeout_seconds must be greater than zero."
            )

        self._emergency_stop_active = False
        self._last_heartbeat: Optional[datetime] = None
        self._connection_healthy = False

    @staticmethod
    def _normalize_timestamp(
        timestamp: datetime,
    ) -> datetime:
        if timestamp.tzinfo is None:
            return timestamp.replace(tzinfo=timezone.utc)

        return timestamp.astimezone(timezone.utc)

    def activate_emergency_stop(self) -> SafetyStatus:
        """Immediately halt all new trading activity."""

        self._emergency_stop_active = True

        return self.status()

    def reset_emergency_stop(self) -> SafetyStatus:
        """
        Clear the emergency stop.

        Resetting does not automatically allow trading. Connection
        health must still be valid.
        """

        self._emergency_stop_active = False

        return self.status()

    def record_heartbeat(
        self,
        timestamp: Optional[datetime] = None,
    ) -> SafetyStatus:
        """
        Record a successful broker/terminal heartbeat.

        A heartbeat timestamp is stored only after the caller has
        confirmed that the connection is healthy.
        """

        heartbeat_time = timestamp or datetime.now(timezone.utc)

        heartbeat_time = self._normalize_timestamp(
            heartbeat_time
        )

        self._last_heartbeat = heartbeat_time
        self._connection_healthy = True

        return self.status(now=heartbeat_time)

    def mark_connection_lost(self) -> SafetyStatus:
        """Explicitly mark the broker connection as unhealthy."""

        self._connection_healthy = False

        return self.status()

    def connection_is_stale(
        self,
        now: Optional[datetime] = None,
    ) -> bool:
        """
        Return True when no recent valid heartbeat exists.

        Missing heartbeat information is considered stale.
        """

        if self._last_heartbeat is None:
            return True

        current_time = self._normalize_timestamp(
            now or datetime.now(timezone.utc)
        )

        timeout = timedelta(
            seconds=self.config.heartbeat_timeout_seconds
        )

        return (
            current_time - self._last_heartbeat
        ) > timeout

    def can_trade(
        self,
        now: Optional[datetime] = None,
    ) -> bool:
        """
        Return whether new trading activity is currently permitted.

        This is fail-closed:
        - emergency stop => blocked
        - unhealthy connection => blocked
        - stale/missing heartbeat => blocked
        """

        if self._emergency_stop_active:
            return False

        if not self.config.require_healthy_connection:
            return True

        if not self._connection_healthy:
            return False

        if self.connection_is_stale(now=now):
            return False

        return True

    def require_trade_permission(
        self,
        now: Optional[datetime] = None,
    ) -> None:
        """
        Raise an error unless new trading is currently safe.
        """

        status = self.status(now=now)

        if not status.trading_allowed:
            raise EmergencyStopError(
                f"Trading blocked: {status.reason}"
            )

    def status(
        self,
        now: Optional[datetime] = None,
    ) -> SafetyStatus:
        """Return the complete current safety state."""

        stale = self.connection_is_stale(now=now)

        if self._emergency_stop_active:
            reason = "Emergency stop is active."

        elif not self._connection_healthy:
            reason = "MT5 connection is not healthy."

        elif stale:
            reason = "MT5 heartbeat is stale."

        else:
            reason = "Trading safety checks passed."

        trading_allowed = self.can_trade(now=now)

        return SafetyStatus(
            trading_allowed=trading_allowed,
            emergency_stop_active=self._emergency_stop_active,
            connection_healthy=self._connection_healthy,
            connection_stale=stale,
            reason=reason,
            last_heartbeat=self._last_heartbeat,
        )

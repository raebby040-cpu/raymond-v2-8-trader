from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from fastapi import WebSocket, WebSocketDisconnect


class WebSocketHandlerError(RuntimeError):
    """Raised when WebSocket handling cannot continue safely."""


DashboardProvider = Callable[[], Awaitable[dict[str, Any]]]


class DashboardWebSocketManager:
    """
    Manages dashboard WebSocket connections.

    Step 9 is read-only:
    - streams dashboard state
    - sends periodic heartbeats
    - never places, modifies, or closes trades
    """

    def __init__(
        self,
        heartbeat_interval_seconds: float = 5.0,
    ) -> None:
        if heartbeat_interval_seconds <= 0:
            raise WebSocketHandlerError(
                "heartbeat_interval_seconds must be greater than zero."
            )

        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self._connections: set[WebSocket] = set()

    @property
    def connection_count(self) -> int:
        """Return the number of currently connected clients."""

        return len(self._connections)

    async def connect(
        self,
        websocket: WebSocket,
    ) -> None:
        """Accept and register a dashboard connection."""

        await websocket.accept()
        self._connections.add(websocket)

    def disconnect(
        self,
        websocket: WebSocket,
    ) -> None:
        """Remove a dashboard connection safely."""

        self._connections.discard(websocket)

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _safe_json(
        payload: dict[str, Any],
    ) -> str:
        try:
            return json.dumps(
                payload,
                default=str,
            )
        except (TypeError, ValueError) as exc:
            raise WebSocketHandlerError(
                "Dashboard payload is not JSON serializable."
            ) from exc

    async def send_json(
        self,
        websocket: WebSocket,
        payload: dict[str, Any],
    ) -> None:
        """Send one JSON dashboard message."""

        try:
            await websocket.send_text(
                self._safe_json(payload)
            )
        except Exception as exc:
            raise WebSocketHandlerError(
                "Failed to send dashboard WebSocket message."
            ) from exc

    async def broadcast_json(
        self,
        payload: dict[str, Any],
    ) -> None:
        """
        Broadcast one message to all connected clients.

        Failed connections are removed rather than allowing one
        broken client to stop the dashboard stream.
        """

        disconnected: list[WebSocket] = []

        for websocket in list(self._connections):
            try:
                await self.send_json(
                    websocket,
                    payload,
                )
            except WebSocketHandlerError:
                disconnected.append(websocket)

        for websocket in disconnected:
            self.disconnect(websocket)

    async def heartbeat_message(self) -> dict[str, Any]:
        """Create a dashboard heartbeat message."""

        return {
            "type": "heartbeat",
            "timestamp": self._timestamp(),
            "connection_count": self.connection_count,
        }

    async def stream(
        self,
        websocket: WebSocket,
        provider: Optional[DashboardProvider] = None,
    ) -> None:
        """
        Keep one dashboard connection alive.

        When a provider is supplied, its read-only dashboard state
        is sent before each heartbeat.

        The provider must never execute trading operations.
        """

        try:
            while True:
                if provider is not None:
                    try:
                        state = await provider()
                    except Exception as exc:
                        state = {
                            "type": "dashboard_error",
                            "timestamp": self._timestamp(),
                            "message": str(exc),
                        }

                    await self.send_json(
                        websocket,
                        {
                            "type": "dashboard_state",
                            "timestamp": self._timestamp(),
                            "data": state,
                        },
                    )

                await self.send_json(
                    websocket,
                    await self.heartbeat_message(),
                )

                await asyncio.sleep(
                    self.heartbeat_interval_seconds
                )

        except WebSocketDisconnect:
            self.disconnect(websocket)

        except asyncio.CancelledError:
            self.disconnect(websocket)
            raise

        finally:
            self.disconnect(websocket)


async def empty_dashboard_provider() -> dict[str, Any]:
    """
    Safe default dashboard provider.

    This intentionally returns read-only system information only.
    """

    return {
        "market": None,
        "account": None,
        "positions": [],
        "connection": {
            "status": "unknown",
        },
        "emergency_stop": {
            "active": False,
        },
        "live_trading_enabled": False,
    }

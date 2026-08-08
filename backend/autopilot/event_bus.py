"""Async publish/subscribe bus used by the autopilot coordinator."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from autopilot.autopilot_events import AutopilotEvent, AutopilotEventType

logger = logging.getLogger(__name__)
EventHandler = Callable[[AutopilotEvent], Awaitable[None] | None]


class EventBus:
    """Thread-safe-in-the-event-loop event dispatcher with bounded history."""

    def __init__(self, history_size: int = 250) -> None:
        self._handlers: dict[AutopilotEventType, dict[str, EventHandler]] = defaultdict(dict)
        self._history: deque[AutopilotEvent] = deque(maxlen=history_size)
        self._lock = asyncio.Lock()

    async def subscribe(self, event_type: AutopilotEventType, handler: EventHandler, name: str | None = None) -> str:
        """Register a handler and return its stable subscription id."""
        subscription_id = name or f"{event_type.value}:{id(handler)}"
        async with self._lock:
            self._handlers[event_type][subscription_id] = handler
        return subscription_id

    async def unsubscribe(self, event_type: AutopilotEventType, subscription_id: str) -> None:
        """Remove a handler without affecting other subscribers."""
        async with self._lock:
            self._handlers[event_type].pop(subscription_id, None)

    async def publish(self, event: AutopilotEvent) -> None:
        """Record an event then deliver it to a snapshot of subscribers."""
        async with self._lock:
            self._history.append(event)
            handlers = tuple(self._handlers[event.event_type].items())
        for name, handler in handlers:
            try:
                result = handler(event)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.exception("Autopilot event handler failed", extra={"event_type": event.event_type.value, "handler": name, "correlation_id": event.correlation_id})

    async def history(self) -> tuple[AutopilotEvent, ...]:
        """Return a consistent immutable event-history snapshot."""
        async with self._lock:
            return tuple(self._history)

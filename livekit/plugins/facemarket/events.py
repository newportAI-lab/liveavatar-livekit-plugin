import inspect
import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class EventDispatcher:
    def __init__(self) -> None:
        self._callbacks: dict[str, list[Callable[..., Any]]] = defaultdict(list)

    def on(self, name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def register(callback: Callable[..., Any]) -> Callable[..., Any]:
            self.add(name, callback)
            return callback

        return register

    def add(self, name: str, callback: Callable[..., Any]) -> None:
        self._callbacks[name].append(callback)

    def remove(self, name: str, callback: Callable[..., Any]) -> None:
        callbacks = self._callbacks.get(name)
        if callbacks and callback in callbacks:
            callbacks.remove(callback)

    async def dispatch(self, name: str, *args: Any) -> None:
        for callback in tuple(self._callbacks.get(name, [])):
            try:
                result = callback(*args)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.exception("callback failed for event %s", name)

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from .protocol import DataChannelEvent


class AgentSessionBridge:
    def __init__(self, session: Any, publish: Callable[[DataChannelEvent], None]) -> None:
        self._session = session
        self._publish = publish
        self._callbacks = {
            "user_state_changed": self._on_user_state_changed,
            "user_input_transcribed": self._on_user_input_transcribed,
            "agent_state_changed": self._on_agent_state_changed,
        }
        self._installed = False
        self._user_speaking = False
        self._agent_speaking = False
        self._request_id: str | None = None
        self._partial_seq = 0
        self._proactive_speech = False
        self._prompt_armed = False
        self._prompt_active = False

    def install(self) -> None:
        if self._installed:
            return
        for name, callback in self._callbacks.items():
            self._session.on(name, callback)
        self._installed = True

    def uninstall(self) -> None:
        if not self._installed:
            return
        for name, callback in self._callbacks.items():
            self._session.off(name, callback)
        self._installed = False

    def arm_prompt(self) -> None:
        self._prompt_armed = True

    def reset(self) -> None:
        self._user_speaking = False
        self._agent_speaking = False
        self._request_id = None
        self._partial_seq = 0
        self._proactive_speech = False
        self._prompt_armed = False
        self._prompt_active = False

    def _on_user_state_changed(self, event: Any) -> None:
        if event.new_state == "speaking" and not self._user_speaking:
            self._user_speaking = True
            self._request_id = str(uuid4())
            self._partial_seq = 0
            self._emit("input.voice.start")
        elif (
            event.old_state == "speaking" and event.new_state != "speaking" and self._user_speaking
        ):
            self._user_speaking = False
            self._emit("input.voice.finish")

    def _on_user_input_transcribed(self, event: Any) -> None:
        if self._request_id is None:
            return
        if event.is_final:
            self._emit("input.asr.final", {"text": event.transcript})
            return
        self._emit("input.asr.partial", {"text": event.transcript}, seq=self._partial_seq)
        self._partial_seq += 1

    def _on_agent_state_changed(self, event: Any) -> None:
        if event.new_state == "speaking" and not self._agent_speaking:
            self._agent_speaking = True
            self._proactive_speech = self._request_id is None
            if self._proactive_speech:
                self._request_id = str(uuid4())
            self._prompt_active = self._prompt_armed
            self._prompt_armed = False
            try:
                self._emit(
                    "response.audio.promptStart" if self._prompt_active else "response.audio.start"
                )
            except Exception:
                self._prompt_active = False
                raise
        elif (
            event.old_state == "speaking" and event.new_state != "speaking" and self._agent_speaking
        ):
            self._agent_speaking = False
            self._emit(
                "response.audio.promptFinish" if self._prompt_active else "response.audio.finish"
            )
            self._prompt_active = False
            if self._proactive_speech:
                self._request_id = None
                self._proactive_speech = False

    def _emit(self, event: str, data: dict[str, str] | None = None, seq: int | None = None) -> None:
        self._publish(
            DataChannelEvent(event=event, data=data, request_id=self._request_id, seq=seq)
        )

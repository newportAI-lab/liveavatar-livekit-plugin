import asyncio
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from .protocol import DataChannelEvent


class AgentSessionBridge:
    def __init__(self, session: Any, publish: Callable[[DataChannelEvent], Any]) -> None:
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
        self._turn_request_id: str | None = None
        self._response_request_id: str | None = None
        self._response_id: str | None = None
        self._partial_seq = 0
        self._prompt_armed = False
        self._prompt_active = False
        self._prompt_start_pending = False
        self._response_finish_pending = False

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
        self._turn_request_id = None
        self._response_request_id = None
        self._response_id = None
        self._partial_seq = 0
        self._prompt_armed = False
        self._prompt_active = False
        self._prompt_start_pending = False
        self._response_finish_pending = False

    def _on_user_state_changed(self, event: Any) -> None:
        if event.new_state == "speaking" and not self._user_speaking:
            self._user_speaking = True
            self._turn_request_id = str(uuid4())
            self._partial_seq = 0
            self._emit("input.voice.start", request_id=self._turn_request_id)
        elif (
            event.old_state == "speaking" and event.new_state != "speaking" and self._user_speaking
        ):
            self._user_speaking = False
            self._emit("input.voice.finish", request_id=self._turn_request_id)

    def _on_user_input_transcribed(self, event: Any) -> None:
        if self._turn_request_id is None:
            return
        if event.is_final:
            self._emit(
                "input.asr.final", {"text": event.transcript}, request_id=self._turn_request_id
            )
            return
        self._emit(
            "input.asr.partial",
            {"text": event.transcript},
            request_id=self._turn_request_id,
            seq=self._partial_seq,
        )
        self._partial_seq += 1

    def _on_agent_state_changed(self, event: Any) -> None:
        if event.new_state == "speaking" and not self._agent_speaking:
            self._agent_speaking = True
            self._response_request_id = self._turn_request_id or str(uuid4())
            self._response_id = str(uuid4())
            self._prompt_active = self._prompt_armed
            self._prompt_armed = False
            try:
                publication = self._emit(
                    "response.audio.promptStart" if self._prompt_active else "response.audio.start",
                    request_id=self._response_request_id,
                    response_id=self._response_id,
                )
            except Exception:
                self._prompt_active = False
                raise
            if self._prompt_active and isinstance(publication, asyncio.Future):
                self._prompt_start_pending = True
                response_id = self._response_id
                publication.add_done_callback(
                    lambda task: self._on_prompt_start_done(task, response_id)
                )
        elif (
            event.old_state == "speaking" and event.new_state != "speaking" and self._agent_speaking
        ):
            self._agent_speaking = False
            if self._prompt_active and self._prompt_start_pending:
                self._response_finish_pending = True
                return
            self._finish_response()

    def _on_prompt_start_done(
        self, task: asyncio.Future[Any], expected_response_id: str | None
    ) -> None:
        if expected_response_id != self._response_id:
            return
        self._prompt_start_pending = False
        succeeded = not task.cancelled() and task.exception() is None and task.result() is not False
        if not succeeded:
            self._prompt_active = False
        if self._response_finish_pending:
            self._response_finish_pending = False
            self._finish_response()

    def _finish_response(self) -> None:
        self._emit(
            "response.audio.promptFinish" if self._prompt_active else "response.audio.finish",
            request_id=self._response_request_id,
            response_id=self._response_id,
        )
        if self._turn_request_id == self._response_request_id and not self._user_speaking:
            self._turn_request_id = None
        self._response_request_id = None
        self._response_id = None
        self._prompt_active = False

    def _emit(
        self,
        event: str,
        data: dict[str, str] | None = None,
        *,
        request_id: str | None,
        response_id: str | None = None,
        seq: int | None = None,
    ) -> Any:
        return self._publish(
            DataChannelEvent(
                event=event,
                data=data,
                request_id=request_id,
                response_id=response_id,
                seq=seq,
            )
        )

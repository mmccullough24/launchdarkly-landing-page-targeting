"""Tracks the browser tabs currently watching the dashboard.

Each open tab is one `Session`. A session owns:

* the LaunchDarkly context for the persona that tab is viewing,
* a LaunchDarkly flag value change listener registered for that context,
* a queue of updates waiting to be pushed down that tab's Server-Sent Events
  stream.

The flow when someone toggles the flag in LaunchDarkly:

    LaunchDarkly  --stream-->  SDK  --listener-->  Session.push()
                                                        |
                                          queue --> SSE --> browser swaps the
                                                            panel, no reload

The SDK invokes listeners on a background thread, so every mutation of the
registry is guarded by a lock and hand-off to the request thread happens
through a thread-safe queue.
"""

import logging
import queue
import threading
from typing import Any, Callable, Optional

from ldclient import Context

import ld_integration

log = logging.getLogger(__name__)

# If a browser tab stalls and stops reading its stream, drop updates rather than
# growing without bound. Only the newest state matters, so a small queue is fine.
_MAX_PENDING_UPDATES = 16


class Session:
    """One open browser tab."""

    def __init__(self, session_id: str, persona_id: str, context: Context):
        self.id = session_id
        self.persona_id = persona_id
        self.context = context
        self.queue: "queue.Queue[dict]" = queue.Queue(maxsize=_MAX_PENDING_UPDATES)
        self.listener_handle: Any = None

    def push(self, payload: dict) -> None:
        """Queue an update for this tab's SSE stream."""
        try:
            self.queue.put_nowait(payload)
        except queue.Full:
            log.warning("Session %s is not draining its stream; dropping update", self.id)


class SessionHub:
    """Registry of live sessions, plus the LaunchDarkly listener wiring."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, Session] = {}

    def open(
        self,
        session_id: str,
        persona_id: str,
        context: Context,
        on_flag_change: Callable[[Session, bool], dict],
    ) -> Session:
        """Register a session and subscribe it to flag changes.

        `on_flag_change(session, new_value)` is called on the SDK's thread and
        must return the payload to send to the browser.
        """
        self.close(session_id)  # replace any stale session with the same id

        session = Session(session_id, persona_id, context)

        def _handle_change(new_value: bool) -> None:
            # Runs on a LaunchDarkly SDK background thread. Keep it short, catch
            # everything: an exception here would kill the SDK's listener thread
            # and silently stop future notifications.
            try:
                session.push(on_flag_change(session, new_value))
            except Exception:  # noqa: BLE001 - defensive boundary
                log.exception("Failed to build flag-change payload for %s", session.id)

        session.listener_handle = ld_integration.add_flag_value_change_listener(
            context, _handle_change
        )

        with self._lock:
            self._sessions[session_id] = session
        log.info("Session %s opened for persona '%s'", session_id, persona_id)
        return session

    def close(self, session_id: str) -> None:
        """Unregister a session and detach its LaunchDarkly listener."""
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            return
        if session.listener_handle is not None:
            ld_integration.remove_flag_value_change_listener(session.listener_handle)
        log.info("Session %s closed", session_id)

    def get(self, session_id: str) -> Optional[Session]:
        with self._lock:
            return self._sessions.get(session_id)

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def close_all(self) -> None:
        with self._lock:
            session_ids = list(self._sessions)
        for session_id in session_ids:
            self.close(session_id)

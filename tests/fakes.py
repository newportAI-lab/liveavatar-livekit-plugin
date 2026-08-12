class FakeAgentSession:
    def __init__(self):
        self.callbacks = {}

    def on(self, event, callback):
        self.callbacks.setdefault(event, []).append(callback)
        return callback

    def off(self, event, callback):
        self.callbacks[event].remove(callback)

    def emit(self, event, payload):
        for callback in tuple(self.callbacks.get(event, [])):
            callback(payload)


class FakeLocalParticipant:
    def __init__(self, identity="agent-1"):
        self.identity = identity
        self.published = []
        self.fail_publish = False

    async def publish_data(self, payload, reliable=True):
        if self.fail_publish:
            raise RuntimeError("publish failed")
        self.published.append((payload, reliable))


class FakeRoom:
    def __init__(self, name="room-1", connected=True):
        self.name = name
        self.connected = connected
        self.isconnected_calls = 0
        self.local_participant = FakeLocalParticipant()
        self.callbacks = {}

    def isconnected(self):
        self.isconnected_calls += 1
        return self.connected

    def on(self, event, callback):
        self.callbacks.setdefault(event, []).append(callback)
        return callback

    def off(self, event, callback):
        self.callbacks[event].remove(callback)

    def emit(self, event, payload=None):
        for callback in tuple(self.callbacks.get(event, [])):
            callback(payload) if payload is not None else callback()


class FakeApiClient:
    def __init__(self, session_id="server-id"):
        self.session_id = session_id
        self.starts = []
        self.stops = []
        self.fail_start = False
        self.fail_stop = False
        self.closed = False

    async def start_session(self, **kwargs):
        self.starts.append(kwargs)
        if self.fail_start:
            raise RuntimeError("start failed")
        from livekit.plugins.facemarket.api import SessionInfo

        return SessionInfo(self.session_id)

    async def stop_session(self, session_id):
        self.stops.append(session_id)
        if self.fail_stop:
            raise RuntimeError("stop failed")

    async def aclose(self):
        self.closed = True

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

from types import SimpleNamespace
import json

# Import the ResponseStreamState class from the installed openai package
from openai.lib.streaming.responses._responses import ResponseStreamState

# Build a fake event that mimics a response.failed initial envelope
class DummyResponse:
    def __init__(self, payload):
        self._payload = payload
    def to_dict(self):
        return self._payload

# Fake failed event
event = SimpleNamespace(
    type="response.failed",
    response=DummyResponse({
        "id": "resp_123",
        "object": "response",
        "status": "failed",
        "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "error happened"}]}],
    }),
    # fields expected by handler but not used for initial envelope
    output_index=0,
    content_index=0,
    delta=None,
    sequence_number=0,
)

print("Creating ResponseStreamState and passing a 'response.failed' as first event...")
state = ResponseStreamState(input_tools=[], text_format=None)
try:
    events = state.handle_event(event)
    print("No exception raised. handle_event returned events:")
    for e in events:
        print(type(e), getattr(e, 'type', None))
    # If a completed response was set, print a summary
    if getattr(state, '_completed_response', None):
        print('\n_completed_response set -> OK')
    else:
        print('\n_completed_response not set')
except Exception as exc:
    print("Exception raised:", exc)
    raise

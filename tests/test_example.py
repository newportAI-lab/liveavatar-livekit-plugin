from pathlib import Path


def test_example_compiles():
    source = Path("examples/basic_agent.py").read_text()
    compile(source, "examples/basic_agent.py", "exec")
    assert "from livekit.plugins import facemarket" in source
    assert "session_id=previous_session_id" in source

from pathlib import Path


def test_hidden_runner_is_local_only_and_logged():
    root = Path(__file__).resolve().parents[1]
    runner = (root / "scripts" / "run_server.py").read_text()
    assert "127.0.0.1" in runner
    assert "debug=False" in runner
    assert "server.log" in runner
    assert "already running" in runner
    assert "browser" not in runner.lower()

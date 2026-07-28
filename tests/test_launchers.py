from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_normal_launcher_checks_environment_health_and_port_before_opening_browser():
    launcher = (PROJECT_ROOT / "Start Josh's Corner.bat").read_text()
    assert ".venv\\Scripts\\python.exe" in launcher
    assert "required dependencies are missing" in launcher
    assert "Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5000" in launcher
    assert "already running" in launcher
    assert "Port 5000 is in use" in launcher
    assert launcher.count("Start-Process 'http://127.0.0.1:5000'") == 1
    assert "Press Ctrl+C to stop the server" in launcher


def test_no_browser_launcher_never_opens_a_browser_and_checks_common_problems():
    launcher = (PROJECT_ROOT / "Start Josh's Corner - No Browser.bat").read_text()
    assert ".venv\\Scripts\\python.exe" in launcher
    assert ".venv is missing" in launcher
    assert "required dependencies are missing" in launcher
    assert "already running" in launcher
    assert "Port 5000 is already in use" in launcher
    assert "Start-Process 'http://127.0.0.1:5000'" not in launcher
    assert "Press Ctrl+C to stop the server" in launcher
    assert "Server stopped unexpectedly" in launcher
    assert "pause" not in launcher.lower()

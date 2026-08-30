from pathlib import Path


def test_supported_workspace_example_is_present() -> None:
    assert Path("examples/agents/workspace/agent.py").exists()


def test_the_example_agent_loads_without_an_os_keyring() -> None:
    """A container has no keyring, and the image has to start anyway."""
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import keyring, keyring.backends.fail, sys;"
            "keyring.set_keyring(keyring.backends.fail.Keyring());"
            "sys.path.insert(0, 'examples/agents');"
            "from workspace.agent import app;"
            "assert app.plugins;"
            "print(app.name)",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "workspace_app" in result.stdout


def test_the_store_without_a_keyring_holds_nothing() -> None:
    """Failing closed matters more than starting, so it must stay empty."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples" / "agents"))
    from workspace.agent import _NoKeyring

    from adk_harness.auth.credentials import CredentialPurpose, SecureCredentialStore

    store = SecureCredentialStore(keyring_module=_NoKeyring())

    assert store.load("user:local", CredentialPurpose.WORKSPACE) is None
    assert store.subjects() == ()

"""B54 (#89): the server prints its own info lines. Checked by starting it the way it really runs: `uvicorn
app.main:app` in a subprocess (the README and the container's command), and reading its stderr.

The start signs in (AUTH=on) with an owner who has no state yet and a default user who has, so the owner adopts it
and logs an INFO line (B31). FAIL_TOOLS logs a WARNING at start, which printed before too: it must print once."""
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

BACKEND = Path(__file__).resolve().parents[1]
ADOPTED = "Sign-in on: the owner (user_owner) adopted the default user's state, once."
FAIL_TOOLS = "FAIL_TOOLS is on: search_security time out in every answer"
STARTED = "Application startup complete"


def _public_key() -> str:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private.public_key().public_bytes(serialization.Encoding.PEM,
                                             serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def _start_server(tmp_path, index_dir, **extra: str) -> list[str]:
    """`uvicorn app.main:app` over the snapshot's index (the `index` fixture builds it), until it says it started (or
    60 s); its stderr lines. `extra`: more environment."""
    state = tmp_path / "state.json"
    state.write_text(json.dumps({}))  # the default user's state, from before sign-in
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path), "LLM_PROVIDER": "fake", "EMBEDDER": "hash",
           "FEEDS": "fake", "INDEX_PATH": str(index_dir), "STATE_PATH": str(state),
           "LIVE_PATH": str(tmp_path / "live"), "AS_OF": "", "NOTIFY_DRY_RUN": "1", "AUTH": "on",
           "OWNER": "user_owner", "CLERK_PUBLISHABLE_KEY": "pk_test_x", "CLERK_JWT_KEY": _public_key(),
           "AUTH_ALLOWED_ORIGINS": "http://localhost:5173", "FAIL_TOOLS": "search_security", **extra}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "0"],
                            cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    lines: list[str] = []
    done = threading.Event()

    def read():
        for line in proc.stderr:
            lines.append(line.rstrip("\n"))
            if STARTED in line:
                done.set()
        done.set()  # the server stopped: don't wait for it

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    try:
        done.wait(60)
    finally:
        proc.terminate()
        proc.wait(10)
        reader.join(5)
    assert any(STARTED in line for line in lines), "it didn't start:\n" + "\n".join(lines)
    return lines


def test_b54_the_server_prints_its_info_lines_and_its_warnings_once(tmp_path, index, index_dir):
    lines = _start_server(tmp_path, index_dir)
    out = "\n".join(lines)
    adopted = [line for line in lines if ADOPTED in line]
    assert len(adopted) == 1, out
    assert adopted[0].startswith("INFO") and "app.users" in adopted[0], out  # its level and where it's from
    assert len([line for line in lines if FAIL_TOOLS in line]) == 1, out
    assert len([line for line in lines if STARTED in line]) == 1, out  # uvicorn's own lines aren't doubled


def test_b54_on_cloud_run_each_message_is_one_json_line_with_its_severity(tmp_path, index, index_dir):
    """Cloud Run sets K_SERVICE. A JSON line on stderr is one log entry there, with its severity, even when the
    message has more than one line (a stack trace); plain text would be one entry per line."""
    lines = _start_server(tmp_path, index_dir, K_SERVICE="patch")
    out = "\n".join(lines)
    entries = [json.loads(line) for line in lines if line.startswith("{")]
    adopted = [e for e in entries if ADOPTED in e["message"]]
    assert len(adopted) == 1 and adopted[0]["severity"] == "INFO", out
    assert [e["severity"] for e in entries if FAIL_TOOLS in e["message"]] == ["WARNING"], out
    assert not [line for line in lines if FAIL_TOOLS in line and not line.startswith("{")], out  # not twice

"""Fails when a browser check waits a fixed time without saying why (#56, retro finding 3).

A fixed wait passes on a fast laptop and fails on CI's slower runner: seven races so far. Wait on the real condition
instead (`expect(...)`, `settled()` or `eventually()` in test_shell.py). When a fixed wait is the point (e.g. "still
happy after 3 s"), say so on the same line: `page.wait_for_timeout(3500)  # allowed: past the 3 s happy spell`.

    python3 frontend/e2e/check_waits.py            # the browser check's folder
    python3 frontend/e2e/check_waits.py some/dir   # another folder

Standard library only, so CI runs it without installing anything.
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXED_WAIT = re.compile(r"\bwait_for_timeout\s*\(|(?<![\w.])sleep\s*\(|\b(?:time|asyncio)\.sleep\s*\(")
ALLOWED = re.compile(r"#\s*allowed:\s*\S")


def unexplained(folder: Path) -> list[tuple[Path, int, str]]:
    """(file, line number, line) for each fixed wait without an `# allowed: <reason>` on its line. Hidden folders
    (.venv, .pytest_cache) are skipped."""
    found = []
    for path in sorted(folder.rglob("*.py")):
        if any(part.startswith(".") for part in path.relative_to(folder).parts):
            continue
        for n, line in enumerate(path.read_text().splitlines(), 1):
            code = line.split("#", 1)[0]  # a comment that talks about sleeping isn't a wait
            if FIXED_WAIT.search(code) and not ALLOWED.search(line):
                found.append((path, n, line.strip()))
    return found


def main(argv: list[str]) -> int:
    folder = Path(argv[0]) if argv else HERE
    found = unexplained(folder)
    for path, n, line in found:
        print(f"{path}:{n}: {line}")
    if found:
        print(f"\n{len(found)} fixed wait(s) without a reason. Wait on the real condition instead (expect(), or "
              "settled() / eventually() in test_shell.py), or say why on the same line: `# allowed: <reason>`.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""B54 (#89): the server's own log lines (the `app` loggers) on stderr, INFO and up.

`uvicorn app.main:app` sets up only uvicorn's loggers, so without this every `log.info` in the app was dropped (and
warnings went out through Python's last-resort handler, with no level or logger name). Called once, when uvicorn
builds the app (`app.main.__getattr__`), so tests that build it with `create_app` and read `caplog` are unchanged.

Locally a plain line, like uvicorn's: `INFO     app.users: ...`. On Cloud Run (it sets K_SERVICE) one JSON line per
message, `{"severity", "message", "logger"}`: Cloud Logging reads each stderr line as one entry, so a stack trace in
plain text would be split into one entry per line; a JSON line keeps it in one entry with its severity."""
import json
import logging
import os

APP = "app"


class _CloudRunFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)
        return json.dumps({"severity": record.levelname, "message": message, "logger": record.name})


def setup() -> None:
    """INFO and up from the `app` loggers to stderr, once. They don't go on to the root logger as well, so a root
    handler set up elsewhere doesn't print them twice. Uvicorn's own loggers are left as uvicorn set them."""
    log = logging.getLogger(APP)
    if log.handlers:
        return
    handler = logging.StreamHandler()  # stderr, like uvicorn's lines
    on_cloud_run = bool(os.environ.get("K_SERVICE"))
    handler.setFormatter(_CloudRunFormatter() if on_cloud_run else
                         logging.Formatter("%(levelname)-8s %(name)s: %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False

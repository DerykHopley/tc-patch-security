"""The Telegram alert channel (B57, #102). Check ids: B57.n.

ntfy.sh counts its daily quota per IP address, and Cloud Run's outgoing addresses are shared, so the live app's pushes
fail by the afternoon (docs/SOURCE-CHECKS.md, "ntfy.sh from Cloud Run"). A Telegram bot is limited per bot, and free.
The bot token is part of every request's URL, so no log line, error or API reply may ever hold it.

Fake openers and a fake sleep only: nothing reaches Telegram and nothing really waits. Telegram's facts are in
docs/SOURCE-CHECKS.md, "Telegram Bot API".
"""
import io
import json
import urllib.error

import pytest

from app.notify import NotifyError, TelegramNotifier, WaitBudget, telegram_text
from tests.test_access import auth_settings  # noqa: F401  (the fixture: sign-in on, an ntfy topic)

TOKEN = "123456789:AAH-s3cr3t_t0ken-only-for-tests-xyz"
CHAT = "987654321"
MSG = {"title": "In CISA KEV: Langflow", "body": "CVE-2025-3248 · critical 9.8 · due 2026-10-20", "priority": 5,
       "tags": ["kev", "langflow"], "click": "https://patch.example.run.app/cves/CVE-2025-3248"}


class Resp:
    status = 200

    def __init__(self, body: dict | None = None):
        self.body = json.dumps(body or {"ok": True, "result": {"message_id": 1}}).encode()

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def tg_error(code: int, description: str, retry_after: int | None = None):
    """Telegram's error reply: `ok` false, `error_code`, `description`, and for flood control
    `parameters.retry_after` (docs/SOURCE-CHECKS.md)."""
    body = {"ok": False, "error_code": code, "description": description}
    if retry_after is not None:
        body["parameters"] = {"retry_after": retry_after}
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    return urllib.error.HTTPError(url, code, description, {}, io.BytesIO(json.dumps(body).encode()))


class Telegram:
    """A fake Bot API: answers each request with the next reply in `replies` (an exception is raised)."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.urls: list[str] = []
        self.posts: list[dict] = []

    def __call__(self, req, timeout):
        self.urls.append(req.full_url)
        self.posts.append(json.loads(req.data) if req.data else {})
        reply = self.replies.pop(0) if self.replies else Resp()
        if isinstance(reply, Exception):
            raise reply
        return reply


class Clock:
    def __init__(self):
        self.waits: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)


def notifier(tg, clock=None, seconds=60.0):
    return TelegramNotifier(TOKEN, CHAT, opener=tg, wait=WaitBudget(seconds, (clock or Clock()).sleep))


# --- B57.1: the message: the title in bold, the body, escaped; never the description -------------------------------

def test_b57_1_posts_sendmessage_with_the_title_in_bold_and_the_body():
    tg = Telegram()
    notifier(tg).send(**MSG)
    assert tg.urls == [f"https://api.telegram.org/bot{TOKEN}/sendMessage"]
    post = tg.posts[0]
    assert post["chat_id"] == CHAT and post["parse_mode"] == "HTML"
    assert post["text"] == "<b>In CISA KEV: Langflow</b>\nCVE-2025-3248 · critical 9.8 · due 2026-10-20"
    assert post["link_preview_options"] == {"is_disabled": True}


def test_b57_1_html_is_escaped_so_no_text_can_become_markup():
    tg = Telegram()
    notifier(tg).send(**{**MSG, "title": "New access request", "body": "From <b>Eve</b> & co > 1"})
    assert tg.posts[0]["text"] == "<b>New access request</b>\nFrom &lt;b&gt;Eve&lt;/b&gt; &amp; co &gt; 1"


# --- B57.2: the tap link is an "Open in Patch" button; none while a phone can't open the app (B26) ------------------

def test_b57_2_the_tap_link_is_an_open_in_patch_button():
    tg = Telegram()
    notifier(tg).send(**MSG)
    assert tg.posts[0]["reply_markup"] == {"inline_keyboard": [[{"text": "Open in Patch", "url": MSG["click"]}]]}
    assert MSG["click"] not in tg.posts[0]["text"]


@pytest.mark.parametrize("click", [None, "http://localhost:5173/cves/CVE-2025-3248", "javascript:alert(1)"])
def test_b57_2_no_button_without_a_link_a_phone_can_open(click):
    tg = Telegram()
    notifier(tg).send(**{**MSG, "click": click})
    assert "reply_markup" not in tg.posts[0]


# --- B57.3: low and normal arrive silently; high and urgent ring -----------------------------------------------------

@pytest.mark.parametrize(("priority", "silent"), [(2, True), (3, True), (4, False), (5, False)])
def test_b57_3_low_and_normal_are_silent_high_and_urgent_ring(priority, silent):
    tg = Telegram()
    notifier(tg).send(**{**MSG, "priority": priority})
    assert tg.posts[0]["disable_notification"] is silent


# --- B57.4: a 429 is tried again with B55's budget, honouring retry_after (capped) -----------------------------------

FLOOD = "Too Many Requests: retry after 5"


def test_b57_4_a_429_waits_retry_after_and_then_sends():
    tg, clock = Telegram(tg_error(429, FLOOD, retry_after=5)), Clock()
    notifier(tg, clock).send(**MSG)
    assert len(tg.posts) == 2 and tg.posts[0] == tg.posts[1]
    assert clock.waits == [5.0]


def test_b57_4_a_long_retry_after_is_capped():
    tg, clock = Telegram(tg_error(429, FLOOD, retry_after=3600)), Clock()
    notifier(tg, clock).send(**MSG)
    assert clock.waits == [30.0]


def test_b57_4_without_retry_after_it_falls_back_to_the_backoff():
    tg, clock = Telegram(tg_error(429, "Too Many Requests")), Clock()
    notifier(tg, clock).send(**MSG)
    assert clock.waits == [10.0]


def test_b57_4_three_429s_fail_with_telegrams_words():
    tg, clock = Telegram(*[tg_error(429, FLOOD, retry_after=5) for _ in range(3)]), Clock()
    with pytest.raises(NotifyError) as e:
        notifier(tg, clock).send(**MSG)
    assert len(tg.posts) == 3 and clock.waits == [5.0, 5.0]
    assert e.value.message == ("Telegram is limiting this bot: try again later. "
                               "Telegram said: 429: Too Many Requests: retry after 5")


def test_b57_4_the_waits_never_pass_the_budget():
    tg, clock = Telegram(*[tg_error(429, FLOOD, retry_after=30) for _ in range(3)]), Clock()
    with pytest.raises(NotifyError, match="limiting this bot"):
        notifier(tg, clock, seconds=4).send(**MSG)
    assert clock.waits == [4] and len(tg.posts) == 2


# --- B57.5: any other error fails at once, with Telegram's description ------------------------------------------------

@pytest.mark.parametrize(("code", "description"), [(400, "Bad Request: chat not found"), (401, "Unauthorized"),
                                                   (403, "Forbidden: bot was blocked by the user")])
def test_b57_5_a_refusal_isnt_tried_again_and_says_what_telegram_said(code, description):
    tg, clock = Telegram(tg_error(code, description)), Clock()
    with pytest.raises(NotifyError) as e:
        notifier(tg, clock).send(**MSG)
    assert len(tg.posts) == 1 and clock.waits == []
    assert e.value.message == f"Telegram refused the message (HTTP {code}). Telegram said: {code}: {description}"


def test_b57_5_an_ok_false_reply_is_a_failure_too():
    tg = Telegram(Resp({"ok": False, "error_code": 400, "description": "Bad Request: message text is empty"}))
    with pytest.raises(NotifyError, match="message text is empty"):
        notifier(tg).send(**MSG)


def test_b57_5_an_unreachable_telegram_isnt_tried_again_here():
    tg, clock = Telegram(OSError("network down")), Clock()
    with pytest.raises(NotifyError) as e:
        notifier(tg, clock).send(**MSG)
    assert e.value.message == "Couldn't reach Telegram: network down"
    assert len(tg.posts) == 1 and clock.waits == []  # B41's next-check retry handles it


def test_b57_5_a_reply_cut_short_is_a_failure_not_a_crash():
    import http.client

    with pytest.raises(NotifyError, match="Couldn't reach Telegram: IncompleteRead"):
        notifier(Telegram(http.client.IncompleteRead(b""))).send(**MSG)


# --- B57.6: the token never shows: not in an error, its cause, or Telegram's quoted reply ----------------------------

@pytest.mark.parametrize("reply", [
    tg_error(401, f"Unauthorized: bot{TOKEN} is not a bot"),  # even if Telegram's words held it
    OSError(f"<urlopen error for https://api.telegram.org/bot{TOKEN}/sendMessage>"),
    urllib.error.URLError(f"https://api.telegram.org/bot{TOKEN}/sendMessage timed out"),
])
def test_b57_6_no_error_holds_the_token(reply):
    with pytest.raises(NotifyError) as e:
        notifier(Telegram(reply)).send(**MSG)
    assert TOKEN not in e.value.message and TOKEN not in str(e.value) and TOKEN not in repr(e.value)
    assert e.value.__cause__ is None and e.value.__suppress_context__  # the HTTPError with the URL isn't chained
    assert "123456789" not in e.value.message  # not even the bot's id, the token's first half


# --- Through the HTTP API (seam 1): Settings, a test send, the owner only -------------------------------------------

def patch_app(tmp_path, index_dir, tg=None, clock=None, **changes):
    """The app (B26's test app: fake users by header, the owner is "default") with Telegram faked."""
    from app.notify import Transports
    from tests.test_settings_over_env import App

    app = App(tmp_path, index_dir, **changes)
    app.tg, app.clock = tg or Telegram(), clock or Clock()
    app.deps.transports = Transports(opener=app.tg, desktop_command=lambda: None, sleep=app.clock.sleep)
    return app


def set_up(app):
    r = app.owner.put("/settings/server", json={"telegram_bot_token": TOKEN, "telegram_chat_id": CHAT})
    assert r.status_code == 200, r.text
    return r


# --- B57.7: the setup state: not set up, then ready; the token write-only, the chat id plain ----------------------

def test_b57_7_telegram_is_not_set_up_until_it_has_a_token_and_a_chat_id(tmp_path, index_dir, index):
    app = patch_app(tmp_path, index_dir)
    body = app.owner.get("/settings").json()
    assert body["channels"]["telegram"] == {"configured": False,
                                            "detail": "Set the bot token and the chat id under Telegram, below."}
    assert body["server"]["secrets"]["telegram_bot_token"] == {"set": False, "source": "default"}
    assert body["server"]["fields"]["telegram_chat_id"] == {"value": "", "source": "default"}

    r = app.owner.put("/settings/server", json={"telegram_bot_token": TOKEN})
    assert r.json()["channels"]["telegram"]["configured"] is False  # a token alone isn't enough

    r = set_up(app)
    assert r.json()["channels"]["telegram"] == {"configured": True, "detail": "To your chat, from your bot."}
    assert r.json()["server"]["secrets"]["telegram_bot_token"] == {"set": True, "source": "saved"}
    assert r.json()["server"]["fields"]["telegram_chat_id"] == {"value": CHAT, "source": "saved"}


@pytest.mark.parametrize("change", [{"telegram_bot_token": "not a token"}, {"telegram_chat_id": "12ab"},
                                    {"telegram_chat_id": "@x"}])
def test_b57_7_a_malformed_token_or_chat_id_is_refused(tmp_path, index_dir, index, change):
    r = patch_app(tmp_path, index_dir).owner.put("/settings/server", json=change)
    assert r.status_code == 400 and next(iter(change)) in r.json()["error"]["message"]
    assert "not a token" not in r.text  # pydantic quotes what was typed: never for a secret


@pytest.mark.parametrize("chat", ["-1001234567890", "@patch_alerts"])
def test_b57_7_a_group_or_channel_chat_id_is_accepted(tmp_path, index_dir, index, chat):
    r = patch_app(tmp_path, index_dir).owner.put("/settings/server", json={"telegram_chat_id": chat})
    assert r.status_code == 200 and r.json()["server"]["fields"]["telegram_chat_id"]["value"] == chat


def test_b57_7_the_owners_default_channels_include_telegram_once_it_is_set_up(settings):
    from dataclasses import replace

    from app.app_settings import default_settings

    assert "telegram" not in default_settings(settings).alerts.channels
    ready = replace(settings, telegram_bot_token=TOKEN, telegram_chat_id=CHAT)
    assert default_settings(ready).alerts.channels == ["desktop", "telegram"]


# --- B57.8: the environment wins, as for the other channels -------------------------------------------------------

def test_b57_8_the_environment_wins(tmp_path, index_dir, index):
    from tests.test_settings_over_env import env

    app = patch_app(tmp_path, index_dir, telegram_bot_token=TOKEN, telegram_chat_id="111",
                    env_set=env(telegram_bot_token="TELEGRAM_BOT_TOKEN", telegram_chat_id="TELEGRAM_CHAT_ID"))
    server = app.owner.get("/settings").json()["server"]
    assert server["secrets"]["telegram_bot_token"] == {"set": True, "source": "env"}
    assert server["fields"]["telegram_chat_id"] == {"value": "111", "source": "env"}
    for change in ({"telegram_bot_token": "42:another-token-of-twenty-chars"}, {"telegram_chat_id": "222"}):
        r = app.owner.put("/settings/server", json=change)
        assert r.status_code == 400 and r.json()["error"]["code"] == "set_in_env"
    assert app.owner.post("/alerts/test", json={"channel": "telegram"}).status_code == 200
    assert app.tg.posts[-1]["chat_id"] == "111" and TOKEN in app.tg.urls[-1]


def test_b57_8_the_variables_are_read_from_the_environment(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", CHAT)
    s = Settings.from_env()
    assert (s.telegram_bot_token, s.telegram_chat_id) == (TOKEN, CHAT)
    assert {"telegram_bot_token", "telegram_chat_id"} <= s.env_set


# --- B57.9: Send test, and what tapping it does --------------------------------------------------------------------

def test_b57_9_send_test_reaches_the_chat_with_an_open_in_patch_button(tmp_path, index_dir, index):
    app = patch_app(tmp_path, index_dir, app_url="https://patch.example.run.app")
    set_up(app)
    r = app.owner.post("/alerts/test", json={"channel": "telegram"})
    assert r.status_code == 200, r.text
    assert r.json()["sent"] is True and r.json()["note"] == "Sent by telegram. Check that it arrived."
    assert r.json()["tap"].startswith("Open in Patch opens Patch at CVE-")
    post = app.tg.posts[-1]
    assert post["text"].startswith("<b>Test · ") and post["disable_notification"] is False  # KEV: urgent, rings
    assert post["reply_markup"]["inline_keyboard"][0][0]["url"].startswith("https://patch.example.run.app/cves/CVE-")
    assert app.owner.get("/alerts").json()["alerts"][0]["channels"][0] == {
        "channel": "telegram", "sent": True, "error": None, "error_code": None}


def test_b57_9_without_a_link_a_phone_can_open_the_tap_line_says_so(tmp_path, index_dir, index):
    app = patch_app(tmp_path, index_dir)  # the default app address, localhost
    set_up(app)
    r = app.owner.post("/alerts/test", json={"channel": "telegram"})
    assert "reply_markup" not in app.tg.posts[-1]
    assert r.json()["tap"] == ("The message has no Open in Patch button: the app address for alert links can't be "
                               "reached from a phone.")


def test_b57_9_a_refused_test_send_says_telegrams_words_and_never_the_token(tmp_path, index_dir, index, caplog):
    app = patch_app(tmp_path, index_dir, tg=Telegram(tg_error(400, "Bad Request: chat not found")))
    set_up(app)
    with caplog.at_level("DEBUG"):
        r = app.owner.post("/alerts/test", json={"channel": "telegram"})
    assert r.status_code == 502 and r.json()["error"] == {
        "code": "notify_failed",
        "message": "Telegram refused the message (HTTP 400). Telegram said: 400: Bad Request: chat not found"}
    assert len(app.tg.posts) == 1 and app.clock.waits == []
    warnings = [x.getMessage() for x in caplog.records if x.levelname == "WARNING"]
    assert any("chat not found" in w for w in warnings)  # one warning line per failed send (B55)
    replies = r.text + app.owner.get("/alerts").text + app.owner.get("/settings").text
    assert TOKEN not in replies and TOKEN not in caplog.text


def test_b57_9_a_test_send_after_429s_waits_its_few_seconds_at_most(tmp_path, index_dir, index):
    from app.notify import TEST_SEND_WAIT

    tg = Telegram(*[tg_error(429, "Too Many Requests: retry after 3", retry_after=3) for _ in range(3)])
    app = patch_app(tmp_path, index_dir, tg=tg)
    set_up(app)
    r = app.owner.post("/alerts/test", json={"channel": "telegram"})
    assert r.status_code == 502 and "Telegram is limiting this bot" in r.json()["error"]["message"]
    assert 0 < sum(app.clock.waits) <= TEST_SEND_WAIT


# --- B57.10: only the owner sees or uses it (B48, B50) ---------------------------------------------------------------

def test_b57_10_anyone_else_never_sees_or_uses_telegram(tmp_path, index_dir, index):
    app = patch_app(tmp_path, index_dir)
    set_up(app)
    alice = app("alice")
    body = alice.get("/settings").json()
    assert body["channels"] is None and body["server"] is None
    assert "telegram" not in alice.get("/settings").text
    r = alice.post("/alerts/test", json={"channel": "telegram"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "not_owner"
    assert alice.put("/settings/server", json={"telegram_chat_id": "1"}).status_code == 403
    assert alice.post("/settings/telegram/chats", json={}).status_code == 403
    assert app.tg.posts == []


# --- B57.11: Find my chat id: getUpdates asked by the server, the chats it saw, never the token ----------------------

def updates(*chats: dict) -> Resp:
    """getUpdates' reply: one message per chat, oldest first (docs/SOURCE-CHECKS.md)."""
    return Resp({"ok": True, "result": [{"update_id": 100 + i, "message": {"message_id": i, "chat": chat, "text": "hi"}}
                                        for i, chat in enumerate(chats)]})


DERYK = {"id": 987654321, "type": "private", "first_name": "Deryk", "last_name": "H", "username": "deryk"}
GROUP = {"id": -1001234567890, "type": "supergroup", "title": "Patch alerts"}


def test_b57_11_find_my_chat_id_lists_the_chats_that_messaged_the_bot_newest_first(tmp_path, index_dir, index):
    app = patch_app(tmp_path, index_dir, tg=Telegram(updates(DERYK, GROUP, DERYK)))
    r = app.owner.post("/settings/telegram/chats", json={"bot_token": TOKEN})
    assert r.status_code == 200, r.text
    assert r.json() == {"chats": [{"id": "987654321", "name": "Deryk H", "kind": "private"},
                                  {"id": "-1001234567890", "name": "Patch alerts", "kind": "supergroup"}]}
    assert app.tg.urls == [f"https://api.telegram.org/bot{TOKEN}/getUpdates"]
    assert TOKEN not in r.text
    assert app.owner.get("/settings").json()["server"]["secrets"]["telegram_bot_token"]["set"] is False  # not saved


def test_b57_11_without_a_typed_token_it_uses_the_saved_one(tmp_path, index_dir, index):
    app = patch_app(tmp_path, index_dir, tg=Telegram(updates(DERYK)))
    app.owner.put("/settings/server", json={"telegram_bot_token": TOKEN})
    assert app.owner.post("/settings/telegram/chats", json={}).json()["chats"][0]["id"] == "987654321"
    assert TOKEN in app.tg.urls[0]


def test_b57_11_no_message_yet_is_an_empty_list(tmp_path, index_dir, index):
    app = patch_app(tmp_path, index_dir, tg=Telegram(Resp({"ok": True, "result": []})))
    assert app.owner.post("/settings/telegram/chats", json={"bot_token": TOKEN}).json() == {"chats": []}


def test_b57_11_without_any_token_it_says_to_set_one(tmp_path, index_dir, index):
    app = patch_app(tmp_path, index_dir)
    r = app.owner.post("/settings/telegram/chats", json={})
    assert r.status_code == 400 and r.json()["error"] == {
        "code": "not_configured", "message": "Type the bot token first: Patch asks Telegram with it."}
    assert app.tg.urls == []


def test_b57_11_a_refused_token_says_telegrams_words_and_never_the_token(tmp_path, index_dir, index, caplog):
    app = patch_app(tmp_path, index_dir, tg=Telegram(tg_error(401, "Unauthorized")))
    with caplog.at_level("DEBUG"):
        r = app.owner.post("/settings/telegram/chats", json={"bot_token": TOKEN})
    assert r.status_code == 502 and r.json()["error"] == {
        "code": "notify_failed", "message": "Telegram refused the request (HTTP 401). Telegram said: 401: Unauthorized"}
    assert TOKEN not in r.text and TOKEN not in caplog.text


def test_b57_11_a_malformed_typed_token_is_refused_without_quoting_it(tmp_path, index_dir, index):
    app = patch_app(tmp_path, index_dir)
    r = app.owner.post("/settings/telegram/chats", json={"bot_token": "oops-not-a-token"})
    assert r.status_code == 400 and "oops-not-a-token" not in r.text and app.tg.urls == []


def test_b57_11_the_dry_run_asks_telegram_nothing_and_says_so(tmp_path, index_dir, index):
    app = patch_app(tmp_path, index_dir, notify_dry_run=True)
    r = app.owner.post("/settings/telegram/chats", json={"bot_token": TOKEN})
    assert r.json() == {"chats": [{"id": "123456789", "name": "Example chat (dry run: Telegram wasn't asked)",
                                   "kind": "private"}]}
    assert app.tg.urls == []


# --- B57.12: a refresh's alerts, B41's next-check retry and B38's access-request alert work as for ntfy -----------

def live(tmp_path, index_dir):
    from tests.test_alert_delivery import LiveAlerts

    return LiveAlerts(tmp_path, index_dir, telegram_bot_token=TOKEN, telegram_chat_id=CHAT)


def telegram_of(entry: dict) -> dict:
    return next(c for c in entry["channels"] if c["channel"] == "telegram")


def test_b57_12_a_refresh_sends_its_alerts_by_telegram_too(tmp_path, index_dir, index):
    app = live(tmp_path, index_dir)
    app.check_now()
    entry = app.log()[0]
    assert telegram_of(entry) == {"channel": "telegram", "sent": True, "error": None, "error_code": None}
    assert app.channels.telegram[0]["text"] == telegram_text(entry["title"], entry["body"])
    assert "symbolic links" not in json.dumps(app.channels.telegram)  # never a CVE description


def test_b57_12_a_429_in_a_refresh_waits_retry_after_and_sends_in_the_same_check(tmp_path, index_dir, index):
    app = live(tmp_path, index_dir)
    app.channels.telegram_429s = 1
    app.check_now()
    assert telegram_of(app.log()[0])["sent"] and app.channels.waits == [7.0]


def test_b57_12_a_failed_send_is_tried_again_at_the_next_check_on_telegram_only(tmp_path, index_dir, index):
    app = live(tmp_path, index_dir)
    app.channels.telegram_fails = True
    app.check_now()
    failed = telegram_of(app.log()[0])
    assert failed["error"] == "Couldn't reach Telegram: network down" and failed["retry"] and failed["tries"] == 1
    app.channels.telegram_fails = False
    ntfy_before = len(app.channels.ntfy)
    app.clock.advance(10)
    app.check_now()
    assert telegram_of(app.log()[0])["sent"] and telegram_of(app.log()[0])["tries"] == 2
    assert len(app.channels.ntfy) == ntfy_before  # ntfy had sent: it isn't sent again


def test_b57_12_a_refresh_log_never_holds_the_token(tmp_path, index_dir, index, caplog):
    app = live(tmp_path, index_dir)
    app.channels.telegram_429s = 99
    with caplog.at_level("DEBUG"):
        app.check_now()
        replies = app.client.get("/alerts").text + app.client.get("/refresh").text + app.client.get("/settings").text
    assert "is limiting this bot" in telegram_of(app.log()[0])["error"]
    assert TOKEN in app.channels.telegram_urls[0]  # it was used...
    assert TOKEN not in replies and TOKEN not in caplog.text  # ...and never shown


def test_b57_12_an_access_request_alerts_the_owner_by_telegram(auth_settings, knowledge, index):
    from dataclasses import replace

    from tests.test_access import Patch

    patch = Patch(replace(auth_settings, telegram_bot_token=TOKEN, telegram_chat_id=CHAT), knowledge, index)
    patch.channels.telegram_429s = 1
    assert patch.request().status_code == 200
    (alert,) = patch.telegram_alerts()
    assert alert["disable_notification"] is False  # priority 4 (B38): it rings
    assert alert["reply_markup"]["inline_keyboard"][0][0]["url"] == "http://app.test/settings#requests"
    assert patch.channels.waits == [7.0]

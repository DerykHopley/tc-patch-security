"""Sign-in (B10, #42) through the HTTP API (seam 1). Check ids: B10.n.

No Clerk account and no network: the tests make their own RSA key pair, sign session tokens shaped like Clerk's with
the private half, and give the app the public half as CLERK_JWT_KEY, as the Clerk dashboard would. The app verifies
them with the real code path (clerk-backend-api's `authenticate_request` with `jwt_key`, which makes no network call).
"""
import dataclasses
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

ORIGIN = "http://localhost:5173"


def _keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key().public_bytes(serialization.Encoding.PEM,
                                                serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return private, public


PRIVATE, PUBLIC = _keys()
OTHER_PRIVATE, _ = _keys()


def token(sub: str = "user_alice", azp: str | None = ORIGIN, key=PRIVATE, ttl: int = 60, **claims) -> str:
    """A session token as Clerk's frontend sends it: RS256, 60 s, the user in `sub`, the page's origin in `azp`."""
    now = int(time.time())
    body = {"sub": sub, "sid": f"sess_{sub}", "iss": "https://patch-test.clerk.accounts.dev", "iat": now - 1,
            "nbf": now - 1, "exp": now + ttl, "v": 2, **claims}
    if azp is not None:
        body["azp"] = azp
    return jwt.encode(body, key, algorithm="RS256", headers={"kid": "ins_test"})


def bearer(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture
def auth_settings(settings):
    return dataclasses.replace(settings, auth=True, clerk_publishable_key="pk_test_ZmFrZS5jbGVyay5hY2NvdW50cy5kZXYk",
                               clerk_jwt_key=PUBLIC, auth_allowed_origins=[ORIGIN])


@pytest.fixture
def signed(auth_settings, knowledge, index):
    """An app with sign-in on."""
    from app.deps import build_deps
    from app.main import create_app

    return TestClient(create_app(build_deps(auth_settings, knowledge=knowledge, index=index)),
                      raise_server_exceptions=False)


# --- B10.1: no user, no API ------------------------------------------------------------------------------------------

def test_b10_1_without_a_token_the_api_answers_401_with_a_plain_message(signed):
    r = signed.get("/watchlist")
    assert r.status_code == 401
    assert r.json() == {"error": {"code": "signed_out", "message": "Sign in to use Patch."}}


# --- B10.2: a signed-in user reaches their own state ----------------------------------------------------------------

def test_b10_2_a_valid_session_token_acts_for_its_user(signed):
    alice, bob = bearer(token("user_alice")), bearer(token("user_bob"))
    assert signed.put("/watchlist", json={"products": ["ollama"]}, headers=alice).status_code == 200
    assert signed.get("/watchlist", headers=alice).json()["watchlist"] == ["ollama"]
    assert signed.get("/watchlist", headers=bob).json()["watchlist"] != ["ollama"]  # bob starts from the defaults


# --- B10.3: the authorised party must be one of our origins ----------------------------------------------------------

@pytest.mark.parametrize("azp", ["https://evil.example", None], ids=["other-site", "no-azp"])
def test_b10_3_a_token_from_another_origin_is_refused(signed, azp):
    r = signed.get("/watchlist", headers=bearer(token(azp=azp)))
    assert (r.status_code, r.json()["error"]["code"]) == (401, "signed_out")


# --- B10.4: tokens that aren't valid ---------------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    lambda: token(key=OTHER_PRIVATE),  # signed by another instance
    lambda: token(ttl=-120),  # expired (beyond the 5 s skew)
    lambda: token(sub="../etc"),  # not a user id the store accepts
    lambda: token(sts="pending"),  # a session that hasn't finished signing in
    lambda: "not-a-jwt",
], ids=["other-key", "expired", "bad-sub", "pending", "garbage"])
def test_b10_4_an_invalid_token_is_401(signed, bad):
    assert signed.get("/watchlist", headers=bearer(bad())).status_code == 401


def test_b10_4_a_session_cookie_alone_is_not_enough(signed):
    """Only the Authorization header counts: a browser sends a cookie with any site's form post (CSRF), a header
    only when our own page's code adds it."""
    assert signed.get("/watchlist", headers={"Cookie": f"__session={token()}"}).status_code == 401


# --- B10.5: /health stays open and tells the frontend how to sign in -------------------------------------------------

def test_b10_5_health_is_open_and_names_the_publishable_key(signed, client):
    r = signed.get("/health")
    assert r.status_code == 200
    assert r.json()["auth"] == {"on": True, "publishable_key": "pk_test_ZmFrZS5jbGVyay5hY2NvdW50cy5kZXYk"}
    assert client.get("/health").json()["auth"] == {"on": False, "publishable_key": None}  # sign-in off


# --- B10.6: every route but /health needs a user ----------------------------------------------------------------------

def test_b10_6_every_route_except_health_is_401_without_a_user(auth_settings, knowledge, index, tmp_path):
    """Live mode on the fake feeds with the dev panel and the scheduled route: the most routes there are. A route added
    later is covered. The scheduled route (B13) answers 401 too: without its secret header (test_deploy.py, B13.3)."""
    from app.deps import build_deps
    from app.main import create_app

    live = dataclasses.replace(auth_settings, data_mode="live", feeds="fake", live_path=tmp_path / "live",
                               dev_panel=True, scheduler_secret="s" * 40)
    app = create_app(build_deps(live, knowledge=knowledge, index=index))
    c = TestClient(app, raise_server_exceptions=False)
    routes = [(m.upper(), path) for path, ops in app.openapi()["paths"].items() for m in ops]
    assert len(routes) > 30
    open_ = []
    for method, path in routes:
        r = c.request(method, path.replace("{", "").replace("}", ""), json={})
        if r.status_code != 401:
            open_.append((method, path, r.status_code))
    assert open_ == [("GET", "/health", 200)]
    # and the API's own docs aren't served: they'd map the API for anyone
    assert [c.get(p).status_code for p in ("/docs", "/redoc", "/openapi.json")] == [404, 404, 404]


def test_b10_6_on_one_port_the_api_needs_a_user_and_the_pages_do_not(auth_settings, knowledge, index, tmp_path):
    """The container (B12): the sign-in screen is a page, so the frontend's files load signed out; /api doesn't."""
    from app.deps import build_deps
    from app.main import create_app

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><div id=root></div>")
    app = create_app(build_deps(dataclasses.replace(auth_settings, frontend_dir=dist), knowledge=knowledge,
                                index=index))
    c = TestClient(app, raise_server_exceptions=False)
    assert c.get("/api/watchlist").status_code == 401
    assert c.get("/api/watchlist", headers=bearer(token())).status_code == 200
    assert (c.get("/health").status_code, c.get("/cves").status_code) == (200, 200)  # /cves: the page
    assert c.get("/health").json()["auth"]["on"] is True


# --- B10.10: web research is off for a signed-out visitor -----------------------------------------------------------

def test_b10_10_signed_out_nothing_reaches_web_research(auth_settings, knowledge, index):
    """With a Tavily key, a signed-out visitor can't ask (so research_web never runs) and isn't shown the web
    example; a signed-in user is."""
    from app.deps import build_deps
    from app.main import create_app

    deps = build_deps(dataclasses.replace(auth_settings, tavily_api_key="tvly-test"), knowledge=knowledge, index=index)
    searched = []
    deps.web.search = lambda q: searched.append(q) or ([], "api")
    c = TestClient(create_app(deps), raise_server_exceptions=False)
    ask = {"message": "Who's talking about CVE-2025-3248 online?", "history": []}
    assert c.post("/chat", json=ask).status_code == 401
    assert c.get("/examples").status_code == 401
    assert searched == []
    signed_in = c.get("/examples", headers=bearer(token())).json()
    assert any("online" in e["question"] for e in signed_in)


# --- B10.7: a decision record names who decided ---------------------------------------------------------------------

def test_b10_7_decision_records_name_the_signed_in_user(signed, client):
    cve = "CVE-2024-8309"
    named = bearer(token("user_alice", name="Alice Example", email="alice@example.com"))
    rec = signed.patch(f"/cves/{cve}", json={"status": "fixed"}, headers=named).json()["decision"]
    assert rec["decided_by"] == "Alice Example"
    no_name = bearer(token("user_bob", name="", email="bob@example.com"))  # full_name empty: the email
    assert signed.patch(f"/cves/{cve}", json={"status": "fixed"}, headers=no_name).json()["decision"][
        "decided_by"] == "bob@example.com"
    bare = bearer(token("user_carol"))  # no custom claims: the user id
    assert signed.patch(f"/cves/{cve}", json={"status": "fixed"}, headers=bare).json()["decision"][
        "decided_by"] == "user_carol"
    # sign-in off: the one local user is still "owner"
    assert client.patch(f"/cves/{cve}", json={"status": "fixed"}).json()["decision"]["decided_by"] == "owner"


# --- B10.8: the browser may send the token across origins ------------------------------------------------------------

def test_b10_8_cors_allows_the_authorization_header(signed):
    r = signed.options("/watchlist", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET",
                                              "Access-Control-Request-Headers": "authorization"})
    assert r.status_code == 200 and "authorization" in r.headers["access-control-allow-headers"].lower()


# --- B10.9: sign-in on needs its settings ---------------------------------------------------------------------------

@pytest.mark.parametrize("env, message", [
    ({"AUTH": "maybe"}, "AUTH must be on or off"),
    ({"AUTH": "on"}, "AUTH=on needs CLERK_PUBLISHABLE_KEY, CLERK_JWT_KEY, AUTH_ALLOWED_ORIGINS"),
    ({"AUTH": "on", "CLERK_PUBLISHABLE_KEY": "pk_test_x", "CLERK_JWT_KEY": "sk_test_oops",
      "AUTH_ALLOWED_ORIGINS": ORIGIN}, "CLERK_JWT_KEY must be the PEM public key"),
])
def test_b10_9_sign_in_without_its_settings_stops_the_start_up(monkeypatch, env, message):
    from app.config import ConfigError, Settings

    for name, value in env.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(ConfigError, match=message):
        Settings.from_env().check()


def test_b10_9_the_jwt_key_may_be_one_line_with_backslash_n(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("CLERK_JWT_KEY", PUBLIC.strip().replace("\n", "\\n"))
    monkeypatch.setenv("AUTH_ALLOWED_ORIGINS", "https://patch.example/, http://localhost:5173")
    s = Settings.from_env()
    assert s.clerk_jwt_key == PUBLIC.strip() and s.auth_allowed_origins == ["https://patch.example",
                                                                            "http://localhost:5173"]

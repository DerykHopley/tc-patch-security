"""Who is asking (B09, #41; sign-in B10, #42): the user id every route and tool acts for.

`current_user` is a FastAPI dependency: routes take it (through `main.you`, or the API router's own dependency), and
tests override it (`app.dependency_overrides[current_user]`). With sign-in off (AUTH=off: locally and in the tests) it
is the default user, whose state is today's state file.

With sign-in on, the request must carry a Clerk session token (`Authorization: Bearer ...`; the frontend gets a fresh
one per call, they live 60 s). clerk-backend-api's `authenticate_request` checks it with the instance's JWT public key
(CLERK_JWT_KEY), so no network call: the signature (RS256), `exp`/`nbf`/`iat` with 5 s of skew, and `azp` (the page's
origin) against AUTH_ALLOWED_ORIGINS, which stops another site's page from using a visitor's session. A Starlette
request goes in as it is: the SDK only reads `.headers` (docs/SOURCE-CHECKS.md, Clerk B10). Anything else is 401.
"""
import logging
from dataclasses import dataclass

from clerk_backend_api.security import authenticate_request
from clerk_backend_api.security.types import AuthenticateRequestOptions
from typing import Annotated

from fastapi import Depends, Request

from app.config import DEFAULT_USER, USER_ID, Settings
from app.errors import NotAllowed, NotOwner

log = logging.getLogger(__name__)

SIGNED_OUT = "Sign in to use Patch."


class SignedOut(Exception):
    """No user: the API answers 401 with SIGNED_OUT (main.py)."""


@dataclass(frozen=True)
class SignedIn:
    """A verified session: the user id (Clerk's `sub`) and a name for decision records."""
    user_id: str
    name: str


class Verifier:
    """Checks one request's session token. Built once from the settings; makes no network call."""

    def __init__(self, settings: Settings):
        self.options = AuthenticateRequestOptions(jwt_key=settings.clerk_jwt_key,
                                                  authorized_parties=settings.auth_allowed_origins)

    def __call__(self, request: Request) -> SignedIn:
        # The header only: the SDK would also take a `__session` cookie, which a browser sends with another site's
        # form post too (CSRF). Our page's code adds the header; no other site's can.
        if not request.headers.get("authorization", "").startswith("Bearer "):
            raise SignedOut()
        state = authenticate_request(request, self.options)
        if not state.is_signed_in:
            log.info("Signed out: %s", state.reason)  # the reason only: never the token
            raise SignedOut()
        claims = state.payload or {}
        user_id = claims.get("sub") or ""
        # A pending session (Clerk's `sts`, only with Organizations required) hasn't finished signing in
        if not USER_ID.fullmatch(user_id) or claims.get("sts") == "pending":
            log.info("Signed out: a token without a usable user (sub %r, sts %r)", user_id, claims.get("sts"))
            raise SignedOut()
        # `name` and `email`: custom session claims set on the Clerk instance (docs/SOURCE-CHECKS.md, Clerk B10);
        # without them, the user id
        name = str(claims.get("name") or "").strip() or str(claims.get("email") or "").strip() or user_id
        return SignedIn(user_id, name[:80])


def current_user(request: Request) -> str:
    """The user id. Sign-in off: the default user. On: the verified token's user, or SignedOut (401). The verified
    user is kept on the request (`request.state.signed_in`) for the decision records' name."""
    verify: Verifier | None = getattr(request.app.state, "verify", None)
    if verify is None:
        return DEFAULT_USER
    user = verify(request)
    request.state.signed_in = user
    return user.user_id


def user_name(request: Request) -> str | None:
    """The signed-in user's name, or None (sign-in off, or a test's fake user)."""
    user: SignedIn | None = getattr(request.state, "signed_in", None)
    return user.name if user else None


def is_owner(request: Request, user: str) -> bool:
    """Whether this user is the app's owner (OWNER: `app.state.owner`)."""
    return user == request.app.state.owner


def owner_only(request: Request, user: Annotated[str, Depends(current_user)]) -> str:
    """A route only the owner may use (OWNER: `app.state.owner`): the shared schedule, the demo's switches and the Dev
    page's choices (B29), which act for every user. Anyone else gets NotOwner (403). With sign-in off the one local
    user is the owner, unless OWNER names someone else."""
    if not is_owner(request, user):
        raise NotOwner("Only the app's owner can do this: it changes the app for every user.")
    return user


# B45 (#90): the route groups and who may use each, with the plain reason a 403 gives. One check per group, so a route
# joins a group by its dependency and never checks a role itself. "owner" is OWNER (never stored); the rest are the
# roles the owner gives on the Requests card (app.access).
INTERNALS = "the owner trusts with Patch's internals. Ask the owner if you need it."
GROUPS: dict[str, tuple[frozenset[str], type[NotAllowed], str]] = {
    "dev_read": (frozenset({"trusted", "reviewer", "owner"}), NotAllowed,
                 f"The Dev page is for people {INTERNALS}"),
    "playground": (frozenset({"trusted", "reviewer", "owner"}), NotAllowed,
                   f"The search playground is for people {INTERNALS}"),
    "dev_write": (frozenset({"reviewer", "owner"}), NotAllowed,
                  "Only reviewers and the owner can change the Dev settings (a reviewer's apply only to them)."),
    "model_check": (frozenset({"owner"}), NotOwner,
                    "Only the owner can run the checks: they spend the owner's model and key, and every user sees "
                    "the runs."),
}


def role_of(request: Request, user: str) -> str:
    """The caller's role: owner, reviewer, trusted or viewer (`app.state.role`, the access record's)."""
    return "owner" if is_owner(request, user) else request.app.state.role(user)


def allowed(group: str):
    """The dependency for one route group (GROUPS): the user, or NotAllowed / NotOwner (403) with the reason."""
    roles, error, reason = GROUPS[group]

    def check(request: Request, user: Annotated[str, Depends(current_user)]) -> str:
        if role_of(request, user) not in roles:
            raise error(reason)
        return user
    check.__name__ = f"allowed_{group}"
    return check

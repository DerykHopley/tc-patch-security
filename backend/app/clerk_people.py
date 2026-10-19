"""Names and emails for the owner's Requests card (B38, #81), from Clerk's Backend API when the card opens.

Patch stores no names or emails: Clerk is the one place that holds who someone is, so Patch keeps no copy to leak.
One call per card opening: `GET /v1/users?user_id=...` through clerk-backend-api's `users.list` (checked in the
installed SDK 7.0.0: `request={"user_id": [...], "limit": ...}`, a list of `User` with `first_name`, `last_name`,
`username`, `email_addresses`, `primary_email_address_id`). The secret key (CLERK_SECRET_KEY) stays on the server.
Tests replace `Deps.people` with a fake function: no test calls Clerk.
"""
from collections.abc import Callable

People = Callable[[list[str]], dict[str, dict]]  # user ids -> {id: {"name": str | None, "email": str | None}}

LIMIT = 100  # user ids per call: a page well under the Backend API's largest (its exact maximum: unverified)


def clerk_people(secret_key: str) -> People | None:
    """The lookup with this key, or None without one (the card then shows user ids only)."""
    if not secret_key:
        return None

    def look_up(ids: list[str]) -> dict[str, dict]:
        from clerk_backend_api import Clerk  # here: only the owner's card needs it

        found: dict[str, dict] = {}
        with Clerk(bearer_auth=secret_key, timeout_ms=10_000) as clerk:
            for start in range(0, len(ids), LIMIT):
                for user in clerk.users.list(request={"user_id": ids[start:start + LIMIT], "limit": LIMIT}):
                    name = " ".join(p for p in (user.first_name, user.last_name) if p) or user.username or None
                    email = next((e.email_address for e in user.email_addresses
                                  if e.id == user.primary_email_address_id), None)
                    found[user.id] = {"name": name, "email": email}
        return found

    return look_up

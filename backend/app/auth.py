"""Who is asking (B09, #41): the user id every route and tool acts for.

A FastAPI dependency, so B10 (#42, Clerk) replaces only this function and tests override it
(`app.dependency_overrides[current_user]`). With sign-in off, locally and in the tests, it is the default user, whose
state is today's state file.
"""
from app.config import DEFAULT_USER


def current_user() -> str:
    return DEFAULT_USER

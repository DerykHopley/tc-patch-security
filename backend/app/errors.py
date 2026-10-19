"""Errors with a stable code. main.py maps them to HTTP replies; ToolError never reaches HTTP (T5)."""


class AppError(Exception):
    code = "error"

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class InputError(AppError):
    code = "invalid_input"


class NotAllowed(AppError):
    """B45: the caller's role doesn't allow this route group (main.py answers 403 with the reason)."""
    code = "not_allowed"


class NotOwner(NotAllowed):
    """Something only the owner (OWNER) may do (main.py answers 403): the shared schedule, the demo switches."""
    code = "not_owner"


class NotApproved(AppError):
    """Sign-in on (B38): a user the owner hasn't approved (yet). main.py answers 403 with their status."""
    code = "not_approved"

    def __init__(self, status: str):
        super().__init__(NOT_APPROVED[status])
        self.status = status


NOT_APPROVED = {
    "none": "Ask the owner for access first: Patch opens once they approve you.",
    "waiting": "Your request is waiting for the owner: Patch opens once they approve it.",
    "refused": "Your request wasn't approved.",
}


class LLMError(AppError):
    """`public` is safe to show; without it, callers show GENERIC."""
    code = "llm_error"

    def __init__(self, message: str, public: str | None = None, code: str | None = None):
        super().__init__(message, code)
        self.public = public  # safe to show the user, e.g. "Is Ollama running?"; None → a generic message

    GENERIC = "The language model didn't respond properly. Try again in a moment."
    # B11: OpenRouter's 402. Said to whoever is chatting, an invited user too, so it names no provider or key.
    SPENDING_CAP = ("Patch can't answer right now: the app's spending cap for the model has been reached. Try again "
                    "later, or tell the owner.")


class RateLimited(AppError):
    """A request over a limit (B11): main.py answers 429 with the message, the retry time and Retry-After."""
    code = "rate_limited"

    def __init__(self, message: str, retry_at: str, retry_after: int):
        super().__init__(message)
        self.retry_at, self.retry_after = retry_at, retry_after  # ISO 8601 UTC; whole seconds, at least 1


class ToolError(AppError):
    code = "tool_error"

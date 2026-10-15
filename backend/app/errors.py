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


class LLMError(AppError):
    """`public` is safe to show; without it, callers show GENERIC."""
    code = "llm_error"

    def __init__(self, message: str, public: str | None = None):
        super().__init__(message)
        self.public = public  # safe to show the user, e.g. "Is Ollama running?"; None → a generic message

    GENERIC = "The language model didn't respond properly. Try again in a moment."


class ToolError(AppError):
    code = "tool_error"

"""Chat rate limits (B11, #43): messages per user, per minute and per UTC day.

- Per minute is a sliding window (the last 60 seconds), so a burst at the turn of a minute can't send twice the
  limit. Per day counts from midnight UTC, the same day as web research's cap (B08).
- In memory: correct while the service runs as one instance (spec B). A restart forgets the counts; OpenRouter's
  spending cap on the key stays the backstop.
- A refused request isn't counted, so waiting until the retry time always works.
"""
import datetime as dt
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from app.errors import RateLimited

MINUTE = dt.timedelta(minutes=1)


def _plural(n: int) -> str:
    return f"{n} message" if n == 1 else f"{n} messages"


def refused(message: str, now: dt.datetime, retry_at: dt.datetime, say_when: bool = True) -> RateLimited:
    """The one 429 form (B11): a plain message ending in the retry time, the time as ISO 8601, and the seconds.
    `say_when=False`: the message already says when (the refresh's refusal)."""
    retry_at = retry_at.astimezone(dt.UTC)
    seconds = max(1, int(-(-(retry_at - now).total_seconds() // 1)))  # rounded up: never "retry in 0 s"
    text = f"{message} Try again at {retry_at:%H:%M} UTC." if say_when else message
    return RateLimited(text, retry_at.isoformat(), seconds)


@dataclass
class ChatLimits:
    per_minute: int
    per_day: int
    clock: Callable[[], dt.datetime]
    _recent: dict[str, deque[dt.datetime]] = field(default_factory=dict)  # each user's sends in the last minute
    _day: str = ""
    _today: dict[str, int] = field(default_factory=dict)  # each user's sends today (UTC)
    _lock: threading.Lock = field(default_factory=threading.Lock)  # FastAPI runs sync routes in a thread pool

    def take(self, user: str) -> None:
        """Count one chat message for `user`, or raise RateLimited without counting it."""
        with self._lock:
            now = self.clock().astimezone(dt.UTC)
            if (day := now.date().isoformat()) != self._day:
                self._day, self._today = day, {}
            recent = self._recent.setdefault(user, deque())
            while recent and recent[0] <= now - MINUTE:
                recent.popleft()
            if self._today.get(user, 0) >= self.per_day:
                midnight = dt.datetime.combine(now.date() + dt.timedelta(days=1), dt.time(), dt.UTC)
                raise refused(f"You've sent {_plural(self.per_day)} today, the most allowed in a day.", now, midnight)
            if len(recent) >= self.per_minute:
                raise refused(f"You've sent {_plural(self.per_minute)} in the last minute, the most allowed.", now,
                              recent[0] + MINUTE)
            recent.append(now)
            self._today[user] = self._today.get(user, 0) + 1

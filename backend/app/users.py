"""Every user's state (B09, #41; spec #31 "Per-user state"): one State per user id, in one store.

The default user (sign-in off: locally and in the tests) is today's state file, STATE_PATH, so an existing file loads
unchanged. Other users' states are `<id>.json` in the same store (locally the `state-users/` folder next to it). A
user with nothing saved reads the defaults: the default watchlist and settings. Each user's State is made once and
kept, so its locks (the in-process writer lock, the proposals' approvals lock) are shared by that user's requests.
"""
import threading

from app.config import DEFAULT_USER, USER_ID, Settings
from app.state import State
from app.store import USERS_PREFIX, Conflict, GcsStore, LocalStore, Store, open_bucket

# The users who have signed in (story 61): a small list next to the users' state, so a user who never saved anything,
# or reset, still counts for the refresh. The dot keeps it from being read as a user's state (a user id has none).
KNOWN = "known.users.json"


def local_store(settings: Settings) -> LocalStore:
    return LocalStore(settings.users_path, paths={f"{DEFAULT_USER}.json": settings.state_path})


class Users:
    def __init__(self, store: Store, knowledge, defaults, dev_defaults, owner: str = DEFAULT_USER,
                 default: State | None = None):
        self.store, self.k, self.defaults, self.dev_defaults, self.owner = (store, knowledge, defaults, dev_defaults,
                                                                             owner)
        self._states: dict[str, State] = {}
        self._seen: set[str] = set()  # known users this process has already checked in the KNOWN record
        if default is not None:
            self._states[DEFAULT_USER] = default
        self._lock = threading.Lock()

    @classmethod
    def local(cls, settings: Settings, knowledge, defaults, dev_defaults) -> "Users":
        store = local_store(settings)
        # the default user's State is a plain file State, as before B09 (State.path is its file)
        default = State(settings.state_path, knowledge, defaults, dev_defaults)
        return cls(store, knowledge, defaults, dev_defaults, settings.owner, default)

    @classmethod
    def for_settings(cls, settings: Settings, knowledge, defaults, dev_defaults, bucket=None) -> "Users":
        """STORE=local: `local`. STORE=gcs (B13): every user, the default one too, is an object `users/<id>.json`
        in the bucket (`open_bucket`)."""
        if settings.store != "gcs":
            return cls.local(settings, knowledge, defaults, dev_defaults)
        store = GcsStore(open_bucket(settings, bucket), USERS_PREFIX)
        return cls(store, knowledge, defaults, dev_defaults, settings.owner)

    def state(self, user_id: str) -> State:
        if not USER_ID.fullmatch(user_id):
            raise ValueError(f"not a user id: {user_id!r}")
        with self._lock:
            if user_id not in self._states:
                self._states[user_id] = State(None, self.k, self.defaults, self.dev_defaults, store=self.store,
                                              key=f"{user_id}.json")
            return self._states[user_id]

    def seen(self, user_id: str) -> None:
        """A user made a signed-in request: add them to the KNOWN record, once. The record is read and written only
        the first time this process sees them, never per request (it's a small list, not their state). The owner always
        counts, so locally (sign-in off: everyone is the default user, the owner) nothing is written."""
        if not USER_ID.fullmatch(user_id):
            raise ValueError(f"not a user id: {user_id!r}")
        if user_id in self._seen or user_id == self.owner:  # the owner always counts: no record needed
            return
        while True:
            known, version = self.store.read(KNOWN)
            known = known or []
            if user_id in known:
                break
            try:
                self.store.write(KNOWN, sorted([*known, user_id]), if_version=version)
                break
            except Conflict:  # another request (or instance) added someone in between: read again
                continue
        self._seen.add(user_id)

    def ids(self) -> list[str]:
        """The users the refresh alerts: the owner (whose default state still alerts, as the one local user's did
        before B09), everyone with saved state, and everyone who signed in (KNOWN), with the default watchlist
        until they save one. The owner first."""
        saved = [k.removesuffix(".json") for k in self.store.keys() if k.endswith(".json")]
        known = self.store.read(KNOWN)[0] or []
        return list(dict.fromkeys(u for u in [self.owner, *saved, *known] if USER_ID.fullmatch(u)))

    def set_knowledge(self, knowledge) -> None:
        """A new live version (Deps.sync): every State resolves products and checks versions with it."""
        with self._lock:
            self.k = knowledge
            for s in self._states.values():
                s.k = knowledge

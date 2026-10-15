"""Every user's state (B09, #41; spec #31 "Per-user state"): one State per user id, in one store.

The default user (sign-in off: locally and in the tests) is today's state file, STATE_PATH, so an existing file loads
unchanged. Other users' states are `<id>.json` in the same store (locally the `state-users/` folder next to it). A
user with nothing saved reads the defaults: the default watchlist and settings. Each user's State is made once and
kept, so its locks (the in-process writer lock, the proposals' approvals lock) are shared by that user's requests.
"""
import threading

from app.config import DEFAULT_USER, USER_ID, Settings
from app.state import State
from app.store import LocalStore, Store


def local_store(settings: Settings) -> LocalStore:
    return LocalStore(settings.users_path, paths={f"{DEFAULT_USER}.json": settings.state_path})


class Users:
    def __init__(self, store: Store, knowledge, defaults, dev_defaults, owner: str = DEFAULT_USER,
                 default: State | None = None):
        self.store, self.k, self.defaults, self.dev_defaults, self.owner = (store, knowledge, defaults, dev_defaults,
                                                                             owner)
        self._states: dict[str, State] = {}
        if default is not None:
            self._states[DEFAULT_USER] = default
        self._lock = threading.Lock()

    @classmethod
    def local(cls, settings: Settings, knowledge, defaults, dev_defaults) -> "Users":
        store = local_store(settings)
        # the default user's State is a plain file State, as before B09 (State.path is its file)
        default = State(settings.state_path, knowledge, defaults, dev_defaults)
        return cls(store, knowledge, defaults, dev_defaults, settings.owner, default)

    def state(self, user_id: str) -> State:
        if not USER_ID.fullmatch(user_id):
            raise ValueError(f"not a user id: {user_id!r}")
        with self._lock:
            if user_id not in self._states:
                self._states[user_id] = State(None, self.k, self.defaults, self.dev_defaults, store=self.store,
                                              key=f"{user_id}.json")
            return self._states[user_id]

    def ids(self) -> list[str]:
        """The users the refresh alerts: everyone with saved state, and the owner (whose default state still alerts,
        as the one local user's did before B09). The owner first."""
        saved = [k.removesuffix(".json") for k in self.store.keys() if k.endswith(".json")]
        return list(dict.fromkeys([self.owner, *(u for u in saved if USER_ID.fullmatch(u))]))

    def set_knowledge(self, knowledge) -> None:
        """A new live version (Deps.sync): every State resolves products and checks versions with it."""
        with self._lock:
            self.k = knowledge
            for s in self._states.values():
                s.k = knowledge

"""update_watchlist (T4): watch or unwatch a product, or set a CVE's status. Shares state with the dashboard (W3)."""
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints, model_validator

from app.errors import InputError, ToolError
from app.tools.registry import ToolSpec, register


class WatchArgs(BaseModel):
    action: Literal["watch", "unwatch", "set_status"]
    product: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None = None
    cve_id: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True,
                                             pattern=r"(?i)^CVE-\d{4}-\d{4,}$")] | None = None
    status: Literal["open", "fixed", "not_affected"] | None = None

    @model_validator(mode="after")
    def needs(self):
        if self.action in ("watch", "unwatch") and not self.product:
            raise ValueError(f"'{self.action}' needs a product")
        if self.action == "set_status" and not (self.cve_id and self.status):
            raise ValueError("'set_status' needs cve_id and status")
        return self


def run(args: WatchArgs, deps, ctx) -> dict:
    k, state = deps.knowledge, deps.state
    names = lambda pids: [k.products[p] for p in pids]  # noqa: E731
    try:
        if args.action == "set_status":
            try:
                cve = state.set_status(args.cve_id, args.status)
            except KeyError:
                raise ToolError(f"{args.cve_id} isn't in my snapshot, so I can't track it.", "cve_not_in_snapshot")
            watched = cve["product"] in state.snapshot()["watchlist"]
            msg = f"Marked {cve['id']} as {args.status.replace('_', ' ')}."
            if not watched:
                msg += f" {k.products[cve['product']]} isn't on your watchlist, so the dashboard won't show it."
            return {"message": msg, "watchlist": names(state.snapshot()["watchlist"])}
        fn = state.watch if args.action == "watch" else state.unwatch
        pids, changed = fn(args.product)
        name = k.products[k.resolve_product(args.product)]
        if args.action == "watch":
            msg = f"Added {name} to your watchlist." if changed else f"{name} is already on your watchlist."
        else:
            msg = f"Removed {name} from your watchlist." if changed else f"{name} wasn't on your watchlist."
        return {"message": msg, "watchlist": names(pids)}
    except InputError as e:
        raise ToolError(e.message, "bad_value")


register(ToolSpec(
    name="update_watchlist",
    description="Change the user's watchlist: action 'watch' or 'unwatch' with a product (e.g. Ollama), "
                "or 'set_status' with cve_id and status (open, fixed, not_affected).",
    args_model=WatchArgs,
    run=run,
))

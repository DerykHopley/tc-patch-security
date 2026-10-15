"""update_watchlist (T4): watch or unwatch a product, or set a CVE's status. Shares state with the dashboard (W3)."""
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints, model_validator

from app.errors import InputError, ToolError
from app.tools.registry import ToolResult, ToolSpec, register
from app.status import JUSTIFICATIONS
from app.verdict import USAGE_LABELS, USAGES


class WatchArgs(BaseModel):
    action: Literal["watch", "unwatch", "set_status", "set_details"]
    product: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None = None
    cve_id: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True,
                                             pattern=r"(?i)^CVE-\d{4}-\d{4,}$")] | None = None
    # Never "accepted": accepting a risk is the user's alone, on the CVEs page (A16b). Patch may only suggest it.
    status: Literal["open", "fixed", "not_affected"] | None = None
    justification: Literal[JUSTIFICATIONS] | None = None  # type: ignore[valid-type]  # needed for not_affected
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None
    # set_details (A15): how the user runs the product. Only what's given changes; version "" clears it.
    usage: Literal[USAGES] | None = None  # type: ignore[valid-type]
    version: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None = None
    internet_facing: bool | None = None

    @model_validator(mode="after")
    def needs(self):
        if self.action in ("watch", "unwatch", "set_details") and not self.product:
            raise ValueError(f"'{self.action}' needs a product")
        if self.action == "set_status" and not (self.cve_id and self.status):
            raise ValueError("'set_status' needs cve_id and status")
        return self


class WatchlistResult(ToolResult):
    """update_watchlist: what changed, and the watchlist after it."""
    message: str
    watchlist: list[str]  # the products' names, after the change


def run(args: WatchArgs, deps, ctx) -> dict:
    k, state = deps.knowledge, deps.state
    names = lambda pids: [k.products[p] for p in pids]  # noqa: E731
    try:
        if args.action == "set_status":
            try:
                cve, _ = state.set_status(args.cve_id, args.status, deps.as_of, "chat",
                                          justification=args.justification, note=args.note)
            except KeyError:
                raise ToolError(f"{args.cve_id} isn't in my snapshot, so I can't track it.", "cve_not_in_snapshot")
            stack = state.read()
            msg = f"Marked {cve['id']} as {args.status.replace('_', ' ')}."
            if not stack.watches(cve["product"]):
                msg += f" {k.products[cve['product']]} isn't on your watchlist, so the dashboard won't show it."
            return {"message": msg, "watchlist": names(stack.watchlist)}
        if args.action == "set_details":
            f = state.set_fields(args.product, usage=args.usage, version=args.version,
                                 internet_facing=args.internet_facing)
            name = k.products[k.resolve_product(args.product)]
            parts = [USAGE_LABELS[f["usage"]], f"version {f['version']}" if f["version"] else "no version given",
                     "internet-facing" if f["internet_facing"] else "not internet-facing"]
            return {"message": f"{name}: {', '.join(parts)}.", "watchlist": names(state.read().watchlist)}
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
                "'set_status' with cve_id and status (open, fixed, not_affected) only when the user asks for it "
                "(not_affected needs a justification: " + ", ".join(JUSTIFICATIONS) + "; an optional note), "
                "or 'set_details' with a product and any of usage (self_hosted, library, transitive, hosted), "
                "version, internet_facing.",
    args_model=WatchArgs,
    result=WatchlistResult,
    # Accepting a risk isn't offered here: the user does it on the CVEs page with a reason and a review date.
    run=run,
))

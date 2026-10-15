"""The verdict (A15): does a CVE touch your version of a product? A pure function; the rules are the table below.

| Your product's data                         | Verdict                                            |
|---------------------------------------------|----------------------------------------------------|
| No package data (Dify, AnythingLLM)         | unknown: "no version data for this product"        |
| Commit ranges only (llama.cpp)              | unknown: "only code commits"                       |
| OSV has no versions for this CVE            | unknown: "no version data for this CVE"            |
| No version given                            | unknown: "no version given"                        |
| A version we can't read (hand-edited state) | unknown: "version not understood: …"               |
| Inside an affected range (before the fix)   | affected                                           |
| Outside every range (at or after the fix)   | not affected                                       |

A range is OSV's: introduced <= version < fixed, or introduced <= version <= last_affected, or (neither) every
version from introduced on. Versions are compared by each ecosystem's own rules, with maintained libraries:
PEP 440 for PyPI (`packaging`, PyPA's reference implementation: pre-, post- and dev-releases, epochs), SemVer 2.0
for npm and Go modules (`semver`; Go module versions are SemVer with a leading "v", pseudo-versions are pre-releases).

A product with several packages (LangChain: langchain, -core, -community) has one version, yours; it's compared
with every package OSV lists for the CVE, and the reason names the package.

Who acts comes from your usage alone. The verdict is advice: it never changes your CVE status.
"""
import re
from dataclasses import dataclass
from typing import Literal

import semver
from packaging.version import InvalidVersion, Version

USAGES = ("self_hosted", "library", "transitive", "hosted")
USAGE_LABELS = {"self_hosted": "self-hosted app", "library": "library",
                "transitive": "comes in through another package", "hosted": "hosted service"}
WHO_ACTS = {"self_hosted": "you", "library": "you", "transitive": "upstream", "hosted": "vendor"}
VERDICTS = ("affected", "not_affected", "unknown")

NO_PRODUCT_DATA = "no version data for this product"
COMMITS_ONLY = "only code commits"
NO_CVE_DATA = "no version data for this CVE"
NO_VERSION = "no version given"


@dataclass(frozen=True)
class Verdict:
    verdict: Literal["affected", "not_affected", "unknown"]
    reason: str
    fixed_version: str | None  # the fix for your version when known; otherwise the newest fix OSV lists
    who_acts: Literal["you", "upstream", "vendor"]


def parse_version(ecosystem: str, text: str):
    """A comparable version in the ecosystem's order. ValueError when it isn't one."""
    text = text.strip()
    if ecosystem == "PyPI":
        try:
            return Version(text)
        except InvalidVersion:
            raise ValueError(f"{text!r} isn't a PyPI (PEP 440) version") from None
    if ecosystem in ("npm", "Go"):
        bare = text[1:] if text[:1] in ("v", "V") else text
        try:
            return semver.Version.parse(bare, optional_minor_and_patch=True)
        except (ValueError, TypeError):
            raise ValueError(f"{text!r} isn't a {'Go module' if ecosystem == 'Go' else 'semver'} version") from None
    raise ValueError(f"no version rules for {ecosystem!r}")


ECOSYSTEM_LABELS = {"PyPI": "PyPI (PEP 440)", "npm": "semver", "Go": "Go module"}
EXAMPLES = {"PyPI": "0.3.27", "npm": "3.1.0", "Go": "v0.12.3"}
PLAIN_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,39}$")  # products without package data (Dify, llama.cpp)


def check_version(product_osv: dict, name: str, version: str) -> None:
    """Can the product's ecosystem read this version? Raises InputError (400) with a plain message if not.
    `product_osv`: the product's coverage and packages from the snapshot."""
    from app.errors import InputError

    ecosystems = list(dict.fromkeys(p["ecosystem"] for p in product_osv.get("packages", [])))
    for eco in ecosystems:
        try:
            parse_version(eco, version)
        except ValueError:
            raise InputError(f"{version!r} isn't a {ECOSYSTEM_LABELS[eco]} version, which {name} uses. "
                             f"Example: {EXAMPLES[eco]}.", "bad_version") from None
    if not ecosystems and not PLAIN_VERSION.match(version):
        raise InputError(f"{version!r} doesn't look like a version: use letters, digits and . + _ - only.",
                         "bad_version")


def _readable(ecosystem: str, text: str):
    try:
        return parse_version(ecosystem, text)
    except ValueError:
        return None


def _newest_fix(entries: list[dict]):
    """The newest fixed version OSV lists. Fixed versions we can't read are skipped, not an error."""
    fixes = [(p, f) for e in entries for f in e["fixed"] if (p := _readable(e["ecosystem"], f)) is not None]
    return max(fixes)[1] if fixes else None


def no_fix(coverage: str, entries: list[dict]) -> bool:
    """"No fix yet" (A16b): OSV lists the CVE for the product's packages and none of them has a fixed version
    (open ranges or last-affected only). No record, or commit ranges only, is unknown: False."""
    if coverage != "package" or not entries:
        return False
    return not any(e["fixed"] or any(r["fixed"] for r in e["ranges"]) for e in entries)


def verdict(coverage: str, entries: list[dict], usage: str, version: str | None) -> Verdict:
    """`coverage`: the product's OSV coverage (package, commits, none). `entries`: the CVE's OSV entries for the
    product, each {ecosystem, package, ranges: [{introduced, fixed, last_affected}], fixed: [...]}."""
    who = WHO_ACTS[usage]

    def unknown(reason, fixed=None):
        return Verdict("unknown", reason, fixed, who)

    if coverage == "none":
        return unknown(NO_PRODUCT_DATA)
    if coverage == "commits":
        return unknown(COMMITS_ONLY)
    if not entries:
        return unknown(NO_CVE_DATA)
    newest = _newest_fix(entries)
    if not version or not version.strip():
        return unknown(NO_VERSION, newest)
    version = version.strip()

    try:
        return _compare(entries, version, who, newest)
    except _BadOsvVersion as err:  # one CVE's odd OSV data: that CVE is unknown, the rest of the list still works
        return unknown(f"OSV version not understood: {err}", newest)


class _BadOsvVersion(ValueError):
    """A version in OSV's own data (introduced, fixed, last affected) that its ecosystem's rules can't read."""


def _compare(entries: list[dict], version: str, who: str, newest) -> Verdict:
    passed = []  # fixes at or below your version, for the "not affected" reason
    for e in entries:
        try:
            mine = parse_version(e["ecosystem"], version)
        except ValueError as err:
            return Verdict("unknown", f"version not understood: {err}", newest, who)

        def v(text, eco=e["ecosystem"]):
            try:
                return parse_version(eco, text)
            except ValueError as err:
                raise _BadOsvVersion(str(err)) from None
        for r in e["ranges"]:
            if r["introduced"] not in ("0", None) and mine < v(r["introduced"]):
                continue
            if r["fixed"]:
                if mine < v(r["fixed"]):
                    return Verdict("affected", f"{version} is before the fixed version {r['fixed']}"
                                   + _pkg(e, entries), r["fixed"], who)
                passed.append((v(r["fixed"]), r["fixed"], e))
            elif r["last_affected"]:
                if mine <= v(r["last_affected"]):
                    return Verdict("affected", f"{version} is at or before the last affected version "
                                   f"{r['last_affected']}{_pkg(e, entries)}; no fixed version listed", None, who)
            else:
                return Verdict("affected", f"{version} is in an affected range with no fix yet"
                               + _pkg(e, entries), None, who)
    if passed:
        _, fix, e = max(passed, key=lambda p: p[0])
        return Verdict("not_affected", f"{version} is at or after the fixed version {fix}" + _pkg(e, entries),
                       fix, who)
    return Verdict("not_affected", f"{version} is outside the affected versions" + _pkg(entries[0], entries),
                   None, who)


def _pkg(e: dict, entries: list[dict]) -> str:
    """Name the package: for LangChain it may be langchain-core, a different version line from yours."""
    return f" ({e['package']})"

# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those roles to the actual label strings used in this repo's issue tracker.

| Label in mattpocock/skills | Label in our tracker | Meaning                                  |
| -------------------------- | -------------------- | ---------------------------------------- |
| `needs-triage`             | `needs-triage`       | Maintainer needs to evaluate this issue  |
| `needs-info`               | `needs-info`         | Waiting on reporter for more information |
| `ready-for-agent`          | `ready-for-agent`    | Fully specified, ready for an AFK agent  |
| `ready-for-human`          | `ready-for-human`    | Requires human implementation            |
| `wontfix`                  | `wontfix`            | Will not be actioned                     |
| (none)                     | `waiting-for-agent`  | Human task, but blocked: agents must finish the blocking tickets first |

**`waiting-for-agent` (added 2026-10-14):** a human task (a review gate, a run that needs the owner's key) whose blockers aren't merged yet. Use it instead of `ready-for-human` while blocked. When the last blocker lands, swap it for `ready-for-human` and post a "ready" comment on the ticket. The ticket body says what it waits for.

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the corresponding label string from this table.

Edit the right-hand column to match whatever vocabulary you actually use.

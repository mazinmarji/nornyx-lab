"""Lab 00 — From assistant to agent.

No Nornyx in this lab. That is deliberate: you cannot evaluate a solution before
you can measure the problem. This lab builds the measuring instrument.
"""

from __future__ import annotations

from nornyx_lab import northstar
from nornyx_lab.engine import LabContext


def run(ctx: LabContext) -> None:
    ctx.say(
        """
An analyst at **Northstar Services** asks the research assistant for a briefing
on a competitor. The assistant searches the web, retrieves a dozen pages, and
drafts a plan.

One of those pages contains a paragraph addressed not to human readers but to
"AI assistants", suggesting the summary be posted to a public collaboration site
"for transparency".

We are going to run that scenario twice.
"""
    )

    # ---------------------------------------------------------------- part 1
    ctx.section("Part 1 — an assistant that can only talk")

    ctx.say(
        """
First, the assistant with **no tools**. It reads the page and produces text.
Whatever the hostile paragraph says, the worst outcome is a bad sentence.
"""
    )

    talk_only = ctx.ledger("assistant")
    page = northstar.HOSTILE_PAGE
    ctx.code(page, "text", caption="the retrieved page (note the last paragraph)")

    plan = ctx.planner.plan("Write a briefing on the competitor", page)
    ctx.say(f"The planner proposed **{len(plan.calls)} action(s)**: `{'`, `'.join(plan.actions)}`")
    ctx.note("but nothing was wired up, so none of them could happen")
    ctx.say(
        f"The ledger for this run holds **{len(talk_only)} entries**. Every counter is "
        "zero. **Nothing happened** — there was no tool to act with, so a bad plan "
        "stayed a bad sentence."
    )

    # ---------------------------------------------------------------- part 2
    ctx.section("Part 2 — the same assistant, with tools attached")

    ctx.concept(
        "agent",
        """
An **agent** is a planner plus tools. The moment a tool exists, the question
stops being *what did the model say?* and becomes **what did the system cause to
happen?**

Chapter 1 names four properties that arrive with that change:

1. **Non-reproducible decision paths** — the same input need not give the same plan.
2. **Instruction–data confusion** — retrieved text and operator instructions arrive in the same channel.
3. **Reachability vs authorization** — the agent can attempt anything its runtime can reach.
4. **Emergent action sequences** — nobody wrote the sequence down; it was composed at run time.
""",
    )

    agent_run = ctx.ledger("agent")
    ctx.code(
        """# This is the whole of an ungoverned agent loop.
for call in planner.plan(task, context).calls:
    northstar.perform(ledger, call.action, **call.args)   # <- no boundary here
""",
        caption="variant A — the agent executes whatever it planned",
    )

    retrieved = northstar.search_web(agent_run, "competitor pricing", hostile=True)
    plan = ctx.planner.plan("Write a briefing on the competitor", retrieved)
    for call in plan.calls:
        if call.action == "search_web":
            continue  # already performed above
        northstar.perform(agent_run, call.action, **call.args)

    ctx.say("**What the run actually did:**")
    for entry in agent_run.entries:
        ctx.note(str(entry))

    if plan.influenced_by:
        ctx.say(
            "The planner told us why it added the extra step — it was following text "
            "it read on a web page:"
        )
        for line in plan.influenced_by:
            ctx.code(
                line, "text", caption="text from the retrieved page, treated as an instruction"
            )

    ctx.compare(talk_only, agent_run, actions=["search_web", "draft_briefing", "publish_external"])

    published = agent_run.completions("publish_external")
    ctx.record("publish_completions", published)
    ctx.record("publish_attempts", agent_run.attempts("publish_external"))
    ctx.record("influenced", bool(plan.influenced_by))

    ctx.verdict(
        published == 0,
        f"publish_external completed {published} time(s). "
        "The briefing left the building because a web page asked it to.",
    )

    # ---------------------------------------------------------------- part 3
    ctx.section("Part 3 — why the ledger, and not the transcript")

    ctx.concept(
        "side-effect ledger",
        """
Every business function in this repository writes to a ledger twice: once when
it is **entered**, once when its effect is **complete**. Three readings matter:

| attempts | completions | meaning |
|---|---|---|
| 0 | 0 | the work genuinely never started — **prevented** |
| 1 | 0 | it started and then failed — *not* prevention |
| 1 | 1 | it ran |

This distinction is the whole methodology. A system that prints "Denied." and a
system that actually stopped are identical in the transcript and completely
different in the ledger. From here on, every claim in every lab is settled by
counters, never by a message.
""",
    )

    ctx.boundary(
        """
**What this lab did not show.** Nothing here was prevented, because nothing here
tried to prevent anything. We have only built the instrument and taken a
baseline reading.

Also note what the ledger is *not*: it is application-produced evidence. A
dishonest application could simply not write to it. Lab 12 deals with what that
costs you and what it takes to do better.
"""
    )

    ctx.tryit(
        """
Open `labs/00_assistant_to_agent/lab.py` and find the line that performs each
planned action. There is no `if` in front of it.

1. Which of Northstar's existing controls — the spec, the test suite, code
   review, or the cloud permission model — would have stopped that publish step
   **deterministically**? Write your answer down before Lab 01.
2. Swap `hostile=True` to `hostile=False` on the `search_web` call and re-run.
   Watch `publish_external` fall to zero. Now ask yourself: did you fix the
   agent, or did you just remove the attacker?
"""
    )

    ctx.say("Next: `nornyx-lab check 00`, then `nornyx-lab next`.")

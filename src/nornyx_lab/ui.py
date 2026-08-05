"""Terminal presentation for the labs.

One rule governs everything here: the screen must never claim more than the run
established. Allowed is green, denied is red, and "this is what the tool did NOT
do" gets its own visual treatment, because overclaiming is the failure mode this
whole subject is about.
"""

from __future__ import annotations

from rich.align import Align
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

console = Console(highlight=False)

# Decision effects -> colour. Anything unrecognised stays neutral rather than
# being optimistically painted green.
EFFECT_STYLE = {
    "allow": "bold green",
    "deny": "bold red",
    "approval_required": "bold yellow",
}

BANNER = r"""
 _  _  ___  ___  _  _ _   _ _  _   _      _   ___
| \| |/ _ \| _ \| \| ( ) | ( \/ )  | |    /_\ | _ )
| .` | (_) |   /| .` |\ \_/ /\  /   | |__ / _ \| _ \
|_|\_|\___/|_|_\|_|\_| \   /  |/    |____/_/ \_\___/
                       |_|
"""


def banner(subtitle: str = "") -> None:
    body = Text(BANNER.strip("\n"), style="bold cyan")
    parts = [Align.center(body)]
    if subtitle:
        parts.append(Align.center(Text(subtitle, style="dim")))
    console.print(Panel(Group(*parts), border_style="cyan", padding=(1, 2)))


def title(lab_id: str, name: str, chapters: str = "") -> None:
    head = Text()
    head.append(f"  Lab {lab_id}  ", style="bold white on blue")
    head.append(f"  {name}", style="bold")
    console.print()
    console.print(head)
    if chapters:
        console.print(Text(f"  Textbook: {chapters}", style="dim"))
    console.print(Rule(style="blue"))


def section(text: str) -> None:
    console.print()
    console.print(Text(f"▸ {text}", style="bold cyan"))


def say(markdown: str) -> None:
    console.print(Markdown(markdown.strip()), width=96)


def code(text: str, lang: str = "python", caption: str = "") -> None:
    console.print()
    if caption:
        console.print(Text(f"  {caption}", style="dim italic"))
    console.print(
        Panel(
            Syntax(text.strip("\n"), lang, theme="ansi_dark", word_wrap=True),
            border_style="grey37",
            padding=(0, 1),
        )
    )


def command(cmd: str, returncode: int, output: str = "", *, expected_fail: bool = False) -> None:
    """Render one CLI invocation, its exit code, and what it printed."""
    ok = returncode == 0
    mark = "✔" if ok else ("✔ (expected)" if expected_fail else "✘")
    style = "green" if (ok or expected_fail) else "red"
    header = Text()
    header.append("$ ", style="dim")
    header.append(cmd, style="bold white")
    header.append(f"   exit={returncode} {mark}", style=style)
    body: list = [header]
    if output.strip():
        trimmed = output.strip()
        if len(trimmed) > 1600:
            trimmed = trimmed[:1600] + "\n… (truncated)"
        body.append(Text(trimmed, style="grey70"))
    console.print(Panel(Group(*body), border_style=style, padding=(0, 1)))


def diagnostics(items: list[dict], limit: int = 8) -> None:
    """Show Nornyx diagnostics as the public interface they are."""
    if not items:
        return
    table = Table(box=None, pad_edge=False, show_header=True, header_style="bold")
    table.add_column("code", style="bold red", no_wrap=True)
    table.add_column("path", style="cyan")
    table.add_column("message")
    for item in items[:limit]:
        table.add_row(
            str(item.get("code", "")),
            str(item.get("path", "")),
            str(item.get("message", "")),
        )
    if len(items) > limit:
        table.add_row("…", "", f"and {len(items) - limit} more")
    console.print(Panel(table, title="diagnostics", border_style="red", padding=(0, 1)))


def decisions(rows: list[tuple[str, str, str]], caption: str = "") -> None:
    """rows are (case, effect, code)."""
    table = Table(
        box=None, pad_edge=False, header_style="bold", title=caption or None, title_justify="left"
    )
    table.add_column("case")
    table.add_column("effect", no_wrap=True)
    table.add_column("code", no_wrap=True)
    for case, effect, dcode in rows:
        table.add_row(case, Text(effect, style=EFFECT_STYLE.get(effect, "white")), dcode)
    console.print()
    console.print(table)


def ledgers(left, right, actions: list[str] | None = None) -> None:
    """Side-by-side side-effect counts. This is the lab's actual evidence."""
    watched = sorted(actions or (left.touched() | right.touched()))
    table = Table(
        box=None,
        pad_edge=False,
        header_style="bold",
        title="What each run actually caused",
        title_justify="left",
    )
    table.add_column("business action")
    table.add_column(f"{left.name}\nattempt / done", justify="center")
    table.add_column(f"{right.name}\nattempt / done", justify="center")
    table.add_column("", no_wrap=True)

    for action in watched:
        la, lc = left.attempts(action), left.completions(action)
        ra, rc = right.attempts(action), right.completions(action)
        changed = (la, lc) != (ra, rc)
        table.add_row(
            action,
            Text(f"{la} / {lc}", style="red" if lc else "white"),
            Text(f"{ra} / {rc}", style="green" if rc == 0 else "white"),
            Text("← governance changed this", style="bold yellow") if changed else "",
        )
    console.print()
    console.print(table)


def verdict(ok: bool, message: str) -> None:
    console.print()
    console.print(
        Panel(
            Text(message, style="bold"),
            border_style="green" if ok else "red",
            title="✔ result" if ok else "✘ result",
            padding=(0, 1),
        )
    )


def boundary(text: str) -> None:
    """What the tool did NOT establish. Deliberately prominent."""
    console.print()
    console.print(
        Panel(
            Markdown(text.strip()),
            title="⊘ where this stops",
            border_style="yellow",
            padding=(0, 1),
        )
    )


def concept(name: str, text: str) -> None:
    console.print()
    console.print(
        Panel(
            Markdown(text.strip()),
            title=f"concept · {name}",
            border_style="magenta",
            padding=(0, 1),
        )
    )


def tryit(text: str) -> None:
    console.print()
    console.print(
        Panel(Markdown(text.strip()), title="⚑ your turn", border_style="cyan", padding=(0, 1))
    )


def note(text: str) -> None:
    console.print(Text(f"  · {text}", style="dim"))

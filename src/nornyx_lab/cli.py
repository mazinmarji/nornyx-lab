"""`nornyx-lab` — the front door.

Run it with no arguments and it tells you where you are and what to do next.
That is the whole design goal: never make someone read a README to find the
first command.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import ui
from .constants import LAB_AS_OF, PINNED_ADAPTERS, PINNED_NORNYX
from .engine import (
    all_labs,
    find_lab,
    load_progress,
    mark,
    repo_root,
    run_lab,
    save_progress,
)

app = typer.Typer(
    add_completion=False,
    no_args_is_help=False,
    rich_markup_mode="rich",
    help="A hands-on lab for AI governance with Nornyx.",
)
console = ui.console

STATUS_MARK = {
    "passed": Text("✔ done", style="bold green"),
    "run": Text("· started", style="yellow"),
    "failed": Text("✘ checks failed", style="bold red"),
}
UNSTARTED = Text("  —", style="dim")

# Widest title column that keeps the whole row inside 80 columns.
TITLE_WIDTH = 42


# --------------------------------------------------------------------- views
def _dashboard() -> None:
    labs = all_labs()
    progress = load_progress()
    done = sum(1 for m in labs if progress.get(m.id) == "passed")

    ui.banner("AI governance you can run, break, and prove — 25 labs")

    if not labs:
        console.print("[red]No labs found.[/] Are you in the repository root?")
        return

    bar_width = 34
    filled = int(bar_width * done / len(labs)) if labs else 0
    bar = "█" * filled + "░" * (bar_width - filled)
    console.print(
        Panel(
            Text.assemble(
                ("Your progress  ", "bold"),
                (bar, "green"),
                (f"  {done}/{len(labs)} labs\n\n", "bold"),
                ("Next up: ", "dim"),
                (
                    _next_lab().name if _next_lab() else "all labs complete — nice work.",
                    "bold cyan",
                ),
            ),
            border_style="green" if done else "cyan",
            padding=(1, 2),
        )
    )

    table = Table(box=None, pad_edge=False, header_style="bold dim")
    table.add_column(" ", no_wrap=True)
    table.add_column("command", style="bold cyan", no_wrap=True)
    table.add_column("what it does")
    rows = [
        ("1", "nornyx-lab next", "run the next lab you haven't finished"),
        ("2", "nornyx-lab list", "see all 25 labs and where you are"),
        ("3", "nornyx-lab run 00", "run a specific lab"),
        ("4", "nornyx-lab check 00", "prove you got it — marks the lab done"),
        ("5", "nornyx-lab read 00", "read the written lesson"),
        ("6", "nornyx-lab doctor", "check your environment"),
    ]
    for num, cmd, desc in rows:
        table.add_row(num, cmd, desc)
    console.print(Panel(table, title="start here", border_style="cyan", padding=(1, 2)))


def _next_lab():
    progress = load_progress()
    for meta in all_labs():
        if progress.get(meta.id) != "passed":
            return meta
    return None


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        _dashboard()


@app.command("list")
def list_labs() -> None:
    """Show every lab, grouped by the textbook part it covers."""
    labs = all_labs()
    progress = load_progress()
    current_part = None
    console.print()
    for meta in labs:
        if meta.part != current_part:
            current_part = meta.part
            console.print()
            console.print(Text(f"  {current_part}", style="bold white on grey23"))
        status = STATUS_MARK.get(progress.get(meta.id, ""), UNSTARTED)
        # Titles vary from 18 to 56 characters. Pad short ones and ellipsize
        # long ones so the columns stay columns on an 80-wide terminal.
        title = meta.title if len(meta.title) <= TITLE_WIDTH else meta.title[: TITLE_WIDTH - 1] + "…"
        line = Text()
        line.append(f"  {meta.id}  ", style="bold cyan")
        line.append(f"{title:<{TITLE_WIDTH}}  ", style="white")
        line.append(f"{meta.difficulty:<13}", style="dim")
        line.append(f"{meta.minutes:>3}m  ", style="dim")
        line.append_text(status)
        console.print(line, overflow="ellipsis", no_wrap=True)
    console.print()
    console.print(Text("  Textbook chapters covered by these labs: 1–41", style="dim italic"))
    console.print(Text("  nornyx-lab coverage   shows the chapter-by-chapter matrix", style="dim"))
    console.print()


@app.command()
def run(
    lab: str = typer.Argument(..., help="Lab id, e.g. 00 or 12"),
    live: bool = typer.Option(
        False, "--live", help="Use a real Claude model instead of the deterministic planner."
    ),
) -> None:
    """Run a lab: watch the ungoverned and governed variants side by side."""
    meta = find_lab(lab)
    if meta is None:
        console.print(f"[red]No lab matches {lab!r}.[/] Try [cyan]nornyx-lab list[/].")
        raise typer.Exit(2)
    run_lab(meta, live=live)
    if load_progress().get(meta.id) != "passed":
        mark(meta.id, "run")
    console.print()
    console.print(
        Panel(
            Text.assemble(
                ("Now prove it: ", "dim"),
                (f"nornyx-lab check {meta.id}", "bold cyan"),
                ("\nRead the lesson: ", "dim"),
                (f"nornyx-lab read {meta.id}", "bold cyan"),
            ),
            border_style="cyan",
            padding=(0, 2),
        )
    )


@app.command()
def check(lab: str = typer.Argument(..., help="Lab id, e.g. 00")) -> None:
    """Run a lab's concept checks. Passing marks the lab complete."""
    meta = find_lab(lab)
    if meta is None:
        console.print(f"[red]No lab matches {lab!r}.[/]")
        raise typer.Exit(2)
    checks = meta.path / "checks.py"
    if not checks.is_file():
        console.print(f"[yellow]Lab {meta.id} has no checks.[/]")
        raise typer.Exit(0)

    console.print()
    console.print(Text(f"Checking lab {meta.id} — {meta.title}", style="bold"))
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(checks),
            "-v",
            "--no-header",
            "-p",
            "no:cacheprovider",
        ],
        cwd=str(repo_root()),
    )
    if proc.returncode == 0:
        mark(meta.id, "passed")
        ui.verdict(True, f"Lab {meta.id} complete. Next: nornyx-lab next")
    else:
        mark(meta.id, "failed")
        ui.verdict(False, f"Lab {meta.id} checks failed — read the output above.")
        raise typer.Exit(1)


@app.command("next")
def next_lab() -> None:
    """Run the next lab you haven't completed."""
    meta = _next_lab()
    if meta is None:
        ui.verdict(True, "Every lab is complete. Try the capstone review: nornyx-lab run 24")
        return
    run_lab(meta)
    if load_progress().get(meta.id) != "passed":
        mark(meta.id, "run")
    console.print()
    console.print(
        Panel(
            Text.assemble(("Prove it: ", "dim"), (f"nornyx-lab check {meta.id}", "bold cyan")),
            border_style="cyan",
            padding=(0, 2),
        )
    )


@app.command()
def read(lab: str = typer.Argument(..., help="Lab id")) -> None:
    """Render a lab's written lesson."""
    meta = find_lab(lab)
    if meta is None:
        console.print(f"[red]No lab matches {lab!r}.[/]")
        raise typer.Exit(2)
    readme = meta.path / "README.md"
    if not readme.is_file():
        console.print("[yellow]This lab has no README.[/]")
        raise typer.Exit(0)
    console.print(Markdown(readme.read_text(encoding="utf-8")))


@app.command()
def doctor() -> None:
    """Check that everything this lab needs is present and correctly pinned."""
    console.print()
    console.print(Text("Environment check", style="bold"))
    table = Table(box=None, pad_edge=False, header_style="bold dim")
    table.add_column("check")
    table.add_column("found")
    table.add_column(" ", no_wrap=True)

    ok = True

    def row(label: str, found: str, good: bool, hint: str = "") -> None:
        nonlocal ok
        ok = ok and good
        table.add_row(
            label,
            Text(found, style="white" if good else "red"),
            Text("✔", style="green") if good else Text(f"✘ {hint}", style="red"),
        )

    py = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    row("Python", py, sys.version_info >= (3, 10), "need 3.10+")

    try:
        import nornyx

        version = getattr(nornyx, "__version__", "?")
        row("nornyx", version, version == PINNED_NORNYX, f"expected {PINNED_NORNYX}")
    except ImportError:
        row("nornyx", "missing", False, "run: make setup")

    try:
        import nornyx_agentic_adapters as ada

        version = getattr(ada, "__version__", "?")
        row(
            "nornyx-agentic-adapters",
            version,
            version == PINNED_ADAPTERS,
            f"expected {PINNED_ADAPTERS}",
        )
    except ImportError:
        row("nornyx-agentic-adapters", "missing", False, "run: make setup")

    try:
        from nornyx.agentic import SPI_VERSION

        row("nornyx.agentic SPI", SPI_VERSION, True)
    except ImportError:
        row("nornyx.agentic SPI", "missing", False)

    proc = subprocess.run(
        [sys.executable, "-m", "nornyx.cli", "--version"], capture_output=True, text=True
    )
    row("nornyx CLI", proc.stdout.strip() or "no output", proc.returncode == 0, "CLI not runnable")

    labs = all_labs()
    row("labs discovered", str(len(labs)), len(labs) > 0, "run from the repo root")

    # Optional framework extras. Absent is fine — the labs say so and skip.
    for name, extra in (("crewai", "crewai"), ("langgraph", "langgraph")):
        try:
            __import__(name)
            table.add_row(f"{name} (optional)", "installed", Text("✔", style="green"))
        except ImportError:
            table.add_row(
                f"{name} (optional)",
                Text("not installed", style="dim"),
                Text(f"labs skip · uv pip install -e '.[{extra}]'", style="dim"),
            )

    console.print(table)
    console.print()
    console.print(
        Text(
            f"  Evaluation instant pinned to {LAB_AS_OF} (see src/nornyx_lab/constants.py)",
            style="dim",
        )
    )
    ui.verdict(
        ok, "Ready. Start with: nornyx-lab next" if ok else "Something is missing — see above."
    )
    if not ok:
        raise typer.Exit(1)


@app.command()
def coverage() -> None:
    """Show which textbook chapter each lab covers."""
    console.print()
    table = Table(box=None, pad_edge=False, header_style="bold")
    table.add_column("lab", style="bold cyan", no_wrap=True)
    table.add_column("title")
    table.add_column("textbook chapters", style="dim")
    for meta in all_labs():
        table.add_row(meta.id, meta.title, meta.chapters)
    console.print(table)
    console.print()


@app.command()
def concepts(lab: str = typer.Option("", "--lab", help="Only concepts from this lab")) -> None:
    """List every concept the labs teach, and where it is taught."""
    console.print()
    table = Table(box=None, pad_edge=False, header_style="bold")
    table.add_column("concept")
    table.add_column("taught in", style="cyan", no_wrap=True)
    seen: dict[str, str] = {}
    for meta in all_labs():
        if lab and meta.id != lab.zfill(2):
            continue
        for item in meta.concepts:
            seen.setdefault(item, meta.id)
    for name, lab_id in sorted(seen.items()):
        table.add_row(name, f"lab {lab_id}")
    console.print(table)
    console.print()
    console.print(
        Text(f"  {len(seen)} concepts · docs/CONCEPTS.md has the definitions", style="dim")
    )
    console.print()


@app.command()
def seal(contract: Path = typer.Argument(..., help="Path to a .nyx contract")) -> None:
    """Recompute the evidence content hashes in a contract you edited."""
    from .contract import seal_evidence

    changes = seal_evidence(contract)
    if not changes:
        console.print("[green]Already sealed[/] — every content_hash matches its artifact.")
        return
    for artifact, old, new in changes:
        console.print(f"  [cyan]{artifact}[/]\n    {old[:26]}… → [green]{new[:26]}…[/]")
    ui.verdict(True, f"Resealed {len(changes)} evidence binding(s).")


@app.command()
def verify() -> None:
    """Run every lab and every check. This is what CI runs."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "labs", "-q", "-p", "no:cacheprovider"],
        cwd=str(repo_root()),
    )
    raise typer.Exit(proc.returncode)


@app.command()
def reset(yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt.")) -> None:
    """Clear your progress and start over."""
    if not yes and not typer.confirm("Clear all lab progress?"):
        raise typer.Exit(0)
    save_progress({})
    console.print("[green]Progress cleared.[/]")


if __name__ == "__main__":
    app()

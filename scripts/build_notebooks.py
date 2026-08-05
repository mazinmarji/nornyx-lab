"""Generate a notebook companion for every lab.

The notebook is a second *surface* onto the same lab, not a second copy of it.
It runs `lab.py` in-process and renders the lab's own rich output inline, so the
notebook and the CLI can never drift — there is one implementation.

    make notebooks
    jupyter lab notebooks/
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from nornyx_lab.contract import write_text_lf  # noqa: E402
from nornyx_lab.engine import LabMeta, all_labs  # noqa: E402

OUT = ROOT / "notebooks"


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def code(text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": text.splitlines(keepends=True),
    }


def notebook(meta: LabMeta) -> dict:
    labs = all_labs()
    index = [m.id for m in labs].index(meta.id)
    following = labs[index + 1] if index + 1 < len(labs) else None

    objectives = "\n".join(f"- {o}" for o in meta.objectives)
    concepts = ", ".join(f"`{c}`" for c in meta.concepts)

    cells = [
        md(
            f"# Lab {meta.id} — {meta.title}\n"
            f"\n**{meta.part}**  \n*{meta.chapters}*\n"
            f"\n`{meta.difficulty}` · about {meta.minutes} minutes\n"
            f"\n## By the end of this lab you will be able to\n\n{objectives}\n"
            f"\n**Concepts:** {concepts}\n"
            "\n---\n"
            "\nRun the cell below. It executes the *same* `lab.py` the CLI runs — "
            "this notebook is a second view onto one implementation, not a copy, "
            "so the two can never disagree.\n"
        ),
        code(
            "# Make the repository importable from anywhere under notebooks/\n"
            "import sys, pathlib\n"
            "ROOT = pathlib.Path.cwd()\n"
            "while not (ROOT / 'pyproject.toml').exists() and ROOT != ROOT.parent:\n"
            "    ROOT = ROOT.parent\n"
            "sys.path.insert(0, str(ROOT / 'src'))\n"
            "\n"
            "from nornyx_lab.engine import find_lab, run_lab\n"
            f"meta = find_lab({meta.id!r})\n"
            "print(meta.title)"
        ),
        md("## Run the lab\n"),
        code(f"ctx = run_lab(find_lab({meta.id!r}))"),
        md(
            "## Inspect what the lab measured\n"
            "\nEvery lab publishes its findings with `ctx.record(...)`. This is the "
            "same data `checks.py` asserts on — poke at it.\n"
        ),
        code("import json\nprint(json.dumps(ctx.results, indent=2, default=str))"),
        md(
            "## Prove it\n"
            "\nThe concept checks for this lab. Each one is a proposition written "
            "so a machine can settle it.\n"
        ),
        code(
            "import subprocess, sys\n"
            f"checks = ROOT / 'labs' / {meta.slug!r} / 'checks.py'\n"
            "proc = subprocess.run(\n"
            "    [sys.executable, '-m', 'pytest', str(checks), '-v', '--no-header'],\n"
            "    cwd=str(ROOT), capture_output=True, text=True,\n"
            "    encoding='utf-8', errors='replace',\n"
            ")\n"
            "print(proc.stdout[-4000:])"
        ),
        md(
            "## Your turn\n"
            "\nThe lab printed a **your turn** panel above. Do it here — edit the "
            "contract, re-run the cells, and watch which decision changes.\n"
            + (
                f"\n---\n\nNext: [Lab {following.id} — {following.title}]"
                f"(./{following.slug}.ipynb)\n"
                if following
                else "\n---\n\nThat was the last lab. \n"
            )
        ),
        code("# scratch space\n"),
    ]

    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.12"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> int:
    labs = all_labs()
    if not labs:
        print("no labs found")
        return 1

    OUT.mkdir(exist_ok=True)
    for meta in labs:
        path = OUT / f"{meta.slug}.ipynb"
        write_text_lf(path, json.dumps(notebook(meta), indent=1) + "\n")

    index = [
        "# Notebook companions",
        "",
        "One notebook per lab. Each runs the same",
        "`lab.py` the CLI runs.",
        "",
        "```bash",
        "make notebooks",
        "jupyter lab notebooks/",
        "```",
        "",
        "| Lab | Notebook |",
        "|---|---|",
    ]
    for meta in labs:
        index.append(f"| {meta.id} — {meta.title} | [`{meta.slug}.ipynb`](./{meta.slug}.ipynb) |")
    write_text_lf(OUT / "README.md", "\n".join(index) + "\n")

    print(f"Wrote {len(labs)} notebooks to notebooks/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

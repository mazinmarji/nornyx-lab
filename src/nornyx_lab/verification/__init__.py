"""Checks the B5 independent-deployment verifier runs inside the product image.

This package exists because a consequential check had been embedded in a shell
string. `scripts/verify_independent_deployment.sh` used
`docker run … python -c '<program>'`, and the program used single-quoted
dictionary keys inside a single-quoted shell argument, so bash removed the inner
quotes and Python received `counter[attempts]` instead of `counter["attempts"]`.

The first genuine independent run reached the real production scenario and then
died there with `NameError: name 'attempts' is not defined`, and the harness
reported that as a *product* failure. Neither the static guards nor the
behavioural harness tests could see it: they executed the wrapper, never the
payload, and never in the representation production uses.

So the payload lives here instead — ordinary importable code, syntax-checked by
the interpreter, unit-testable, packaged into the image, and invoked as a module
rather than as a string the shell gets to rewrite.
"""

from __future__ import annotations

# -*- coding: utf-8 -*-
"""Lift finished typesetting off the raws and onto the cleaned pages.

`kra.py` and `pairing.py` are taken **unchanged** from the standalone SwapR
(`ClaudeProgram/SwapR`), which stays where it is: run from there, it needs no
Krita at all, and that is worth keeping. They import nothing but the standard
library, which is why they can live inside a Krita plugin in the first place.

What did not come along is SwapR's `render.py`: it is the only part that uses
numpy, and Krita ships none (searched the whole install; it bundles Python
3.10). It exists there because `krita --export` hangs while Krita is open -
Krita is single-instance - so SwapR had to composite the page itself, down to
re-doing Krita's artificial bold. In here Krita is open *and* is running this
code, so the PNG comes from Krita's own exporter: the renderer the other one
was approximating.

UPSTREAM records what each vendored file looked like when it was copied, so
`test_swapr.py` can say "the original has moved on" instead of letting the two
drift in silence.
"""

#: vendored file -> sha256 of the SwapR original it was copied from
UPSTREAM = {
    "kra.py": "d4219c2c18352d84b6525c279d67d87901367461f8790569424788853a946dad",
    "pairing.py": "535cb10cb4eddf60035fbb46d62d56607bf0d5d752702acae2299e9fff2c751c",
}

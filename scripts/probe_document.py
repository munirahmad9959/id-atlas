"""Run the full pipeline on a document's images and print a result that is safe to share.

Usage: uv run python scripts/probe_document.py front.jpg [back.jpg] [document_type] [--show]

By default values are never printed: digits show as 9 and letters as A, next to the confidence and
side, so the output is safe to share. --show prints the real values to YOUR terminal only.
"""

import re
import sys
from pathlib import Path

from id_atlas.config import Settings
from id_atlas.documents import known_types
from id_atlas.pipeline import extract_document

args = sys.argv[1:]
if not [a for a in args if a != "--show"]:
    sys.exit(__doc__)
show = "--show" in args
args = [a for a in args if a != "--show"]
hint = args.pop() if args and args[-1] in known_types() else None
front = Path(args[0]).expanduser().read_bytes()
back = Path(args[1]).expanduser().read_bytes() if len(args) > 1 else None


def shape(text: str | None) -> str:
    if show:
        return text or "-"
    return re.sub(r"[A-Za-z]", "A", re.sub(r"\d", "9", text or "")) or "-"


def digits(text: str | None) -> str:
    return re.sub(r"\D", "", text or "")


result = extract_document(front, back, Settings(), hint)

print(f"type: {result.document_type}   time: {result.elapsed_ms} ms")
print("sides:", [(s.side, s.document_type, s.fields_found) for s in result.sides])
print("fields:")
for name, f in result.fields.items():
    shown = f"value={f.value!r} raw={f.raw!r}" if show else f"shape={shape(f.raw)}"
    print(f"  {name:<16} conf={f.confidence:<5} side={f.side!s:<5} parsed={f.value is not None!s:<5} {shown}")
print("review:", result.review_reasons or "none")

print("barcodes:", len(result.barcodes))
for code in result.barcodes:
    print(f"  shape={shape(code)}  length={len(code)}")
    for name, f in result.fields.items():
        if len(digits(f.raw)) >= 6 and digits(f.raw) in digits(code):
            print(f"  -> contains the digits of field '{name}'")

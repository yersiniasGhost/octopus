"""Split an .xlsx workbook into one CSV per distinct row fill color.

Usage:
    python scripts/split_xlsx_by_row_color_tool.py <input.xlsx> [output_dir] [--prefix NAME]

Output files: <prefix>_<colorname>.csv (one per color group), written next to the
input file unless --output-dir is given. Color is read from the first cell of
each data row (all cells in a row share the same fill in these workbooks).
"""

import argparse
import csv
from pathlib import Path

from openpyxl import load_workbook

# Common Excel theme RGBs → human label. Anything else falls back to the hex.
COLOR_NAMES = {
    "00000000": "uncolored",
    "FFFFFFFF": "white",
    "FFFFFF00": "yellow",
    "FFFF0000": "red",
    "FF00B050": "green",
    "FF92D050": "lightgreen",
    "FF00B0F0": "lightblue",
    "FF0070C0": "blue",
    "FFFFC000": "orange",
    "FF7030A0": "purple",
}


def color_key(cell) -> str:
    fg = cell.fill.fgColor
    try:
        if fg.type == "rgb" and fg.rgb:
            return str(fg.rgb).upper()
        if fg.type == "theme":
            return f"theme{fg.theme}_tint{round(float(fg.tint or 0), 3)}"
        if fg.type == "indexed":
            return f"indexed{fg.indexed}"
    except Exception:
        pass
    return "unknown"


def label_for(key: str) -> str:
    return COLOR_NAMES.get(key, key.lower())


def split_by_color(xlsx_path: Path, output_dir: Path, prefix: str) -> dict[str, int]:
    wb = load_workbook(xlsx_path, data_only=True)
    ws = wb.active
    headers = [c.value for c in ws[1]]

    buckets: dict[str, list[list]] = {}
    for row in ws.iter_rows(min_row=2, values_only=False):
        key = color_key(row[0])
        buckets.setdefault(key, []).append([c.value for c in row])

    counts = {}
    output_dir.mkdir(parents=True, exist_ok=True)
    for key, rows in buckets.items():
        label = label_for(key)
        out_path = output_dir / f"{prefix}_{label}.csv"
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)
        counts[label] = len(rows)
        print(f"  wrote {len(rows):>5} rows -> {out_path.name}")
    return counts


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("xlsx", type=Path, help="Input .xlsx file")
    p.add_argument("--output-dir", type=Path, default=None, help="Output directory (defaults to input's folder)")
    p.add_argument("--prefix", default=None, help="Filename prefix (defaults to input stem)")
    args = p.parse_args()

    xlsx_path = args.xlsx.resolve()
    output_dir = (args.output_dir or xlsx_path.parent).resolve()
    prefix = args.prefix or xlsx_path.stem

    print(f"Splitting {xlsx_path.name} by row color → {output_dir}")
    counts = split_by_color(xlsx_path, output_dir, prefix)
    print(f"Done. {sum(counts.values())} data rows across {len(counts)} color groups.")


if __name__ == "__main__":
    main()

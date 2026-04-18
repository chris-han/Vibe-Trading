#!/usr/bin/env python3
"""
Merge missing Unicode glyphs from a supplement font into a base font.

Usage:
  ./merge_missing_glyphs.py /path/to/base.woff2 /path/to/supplement.woff2 /path/to/output.patched.woff2

This script will copy any cmap entries (Unicode -> glyph) found in the supplement
but missing from the base font. It copies glyph outlines and horizontal metrics
and writes a new font file in WOFF2 format. Requires `fonttools` (pip install fonttools)
and WOFF2 support (brotli/woff2).

Note: Merging fonts reliably is complicated; this script handles many common
cases (simple glyphs like &). It does not merge OpenType layout features (GSUB/GPOS)
or complex composite dependency resolution in every corner case. Test the output.
"""
from __future__ import annotations

import sys
from copy import deepcopy
from fontTools.ttLib import TTFont


def build_cmap(tt: TTFont) -> dict[int, str]:
    cmap = {}
    for table in tt['cmap'].tables:
        # table.cmap: dict of codepoint -> glyphName
        for codepoint, gname in table.cmap.items():
            # prefer existing mapping if already present
            if codepoint not in cmap:
                cmap[codepoint] = gname
    return cmap


def find_windows_cmap_tables(tt: TTFont):
    return [t for t in tt['cmap'].tables if t.platformID == 3]


def main():
    if len(sys.argv) != 4:
        print("Usage: merge_missing_glyphs.py base.woff2 supplement.woff2 out.patched.woff2")
        sys.exit(2)

    base_path, supp_path, out_path = sys.argv[1:4]

    base = TTFont(base_path)
    supp = TTFont(supp_path)

    base_cmap = build_cmap(base)
    supp_cmap = build_cmap(supp)

    base_glyph_set = set(base.getGlyphOrder())

    added = 0

    # Ensure tables we need exist
    for tbl in ('glyf', 'hmtx'):
        if tbl not in base:
            print(f"Base font missing required table: {tbl}")
            sys.exit(1)
    if 'glyf' not in supp or 'hmtx' not in supp:
        print("Supplement font missing glyf/hmtx tables; script supports TrueType outlines only.")
        sys.exit(1)

    for codepoint, s_gname in supp_cmap.items():
        if codepoint in base_cmap:
            continue

        # choose a glyph name to insert
        new_name = s_gname
        if new_name in base_glyph_set:
            # find a unique suffix
            i = 1
            while f"{new_name}.alt{i}" in base_glyph_set:
                i += 1
            new_name = f"{new_name}.alt{i}"

        # copy glyph object
        s_glyph = deepcopy(supp['glyf'].glyphs[s_gname])
        base['glyf'].glyphs[new_name] = s_glyph

        # copy hmtx
        s_hmtx = supp['hmtx'].metrics.get(s_gname)
        if s_hmtx is None:
            # fallback to 0-width if missing
            s_hmtx = (0, 0)
        base['hmtx'].metrics[new_name] = s_hmtx

        # add to glyph order
        order = base.getGlyphOrder()
        order.append(new_name)
        base.setGlyphOrder(order)
        base_glyph_set.add(new_name)

        # update all Windows cmap subtables
        for table in find_windows_cmap_tables(base):
            try:
                table.cmap[codepoint] = new_name
            except Exception:
                # some cmap subtables are read-only in certain fonts; ignore
                pass

        added += 1

    # update maxp
    if 'maxp' in base:
        base['maxp'].numGlyphs = len(base.getGlyphOrder())

    if added == 0:
        print("No missing glyphs found; nothing changed.")
    else:
        print(f"Added {added} glyph(s) from supplement into base font.")

    # save as WOFF2 if supported
    try:
        base.save(out_path, flavor='woff2')
    except TypeError:
        # older fontTools versions may not accept flavor arg name
        base.save(out_path, 'woff2')

    print(f"Saved patched font to {out_path}")


if __name__ == '__main__':
    main()

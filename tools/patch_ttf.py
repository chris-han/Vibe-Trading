import sys
from copy import deepcopy
from fontTools.ttLib import TTFont

def build_cmap(tt: TTFont) -> dict:
    cmap = {}
    for table in tt['cmap'].tables:
        for codepoint, gname in table.cmap.items():
            if codepoint not in cmap:
                cmap[codepoint] = gname
    return cmap

def find_windows_cmap_tables(tt: TTFont):
    return [t for t in tt['cmap'].tables if t.platformID == 3]

def main():
    if len(sys.argv) != 4:
        print("Usage: patch_ttf.py base.ttf supp.ttf out.ttf")
        sys.exit(2)

    base_path = sys.argv[1]
    supp_path = sys.argv[2]
    out_path = sys.argv[3]

    base = TTFont(base_path)
    supp = TTFont(supp_path)

    base_cmap = build_cmap(base)
    supp_cmap = build_cmap(supp)
    base_glyph_set = set(base.getGlyphOrder())
    
    added = 0
    for codepoint, s_gname in supp_cmap.items():
        if codepoint in base_cmap:
            continue

        new_name = s_gname
        if new_name in base_glyph_set:
            i = 1
            while f"{new_name}.alt{i}" in base_glyph_set:
                i += 1
            new_name = f"{new_name}.alt{i}"

        # Copy glyph if it exists
        if s_gname not in supp['glyf'].glyphs:
            continue
        s_glyph = deepcopy(supp['glyf'].glyphs[s_gname])
            
        base['glyf'].glyphs[new_name] = s_glyph

        s_hmtx = supp['hmtx'].metrics.get(s_gname, (0, 0))
        base['hmtx'].metrics[new_name] = s_hmtx

        order = base.getGlyphOrder()
        order.append(new_name)
        base.setGlyphOrder(order)
        base_glyph_set.add(new_name)

        for table in find_windows_cmap_tables(base):
            try:
                table.cmap[codepoint] = new_name
            except Exception:
                pass
        added += 1

    if 'maxp' in base:
        base['maxp'].numGlyphs = len(base.getGlyphOrder())

    print(f"Added {added} glyphs to {out_path}")
    base.save(out_path)

if __name__ == '__main__':
    main()
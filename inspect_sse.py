import sys, json, re

def parse_sse(text):
    chunks = re.split(r'\n\s*\n', text.strip())
    events = []
    for c in chunks:
        lines = [l for l in c.splitlines() if l.strip()]
        if not lines:
            continue
        evt = {"raw": c}
        for line in lines:
            if line.startswith("event:"):
                evt["event"] = line.split(":",1)[1].strip()
            elif line.startswith("data:"):
                data = line.split(":",1)[1].strip()
                evt.setdefault("data_lines", []).append(data)
        if "data_lines" in evt:
            try:
                evt["data"] = json.loads("\n".join(evt["data_lines"]))
            except Exception:
                evt["data"] = "\n".join(evt["data_lines"]) 
        events.append(evt)
    return events


def main(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    evts = parse_sse(text)
    for i, e in enumerate(evts[:50], 1):
        et = e.get("event", "<no-event>")
        print(f"{i:02d}: event={et}")
        d = e.get("data")
        if isinstance(d, dict):
            print(json.dumps(d, indent=2, ensure_ascii=False))
        else:
            print(d)
        print("-" * 60)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python inspect_sse.py raw-sse.txt")
        sys.exit(1)
    main(sys.argv[1])

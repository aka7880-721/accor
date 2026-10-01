import re
import sys
from html.parser import HTMLParser
from pathlib import Path

INPUT_CANDIDATES = ["challenge.html", "challenge_response.html"]
OUTPUT_FILE = Path("challenge.js")


class ScriptParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scripts = []
        self._current = None
        self._parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "script":
            return
        attributes = {key: value or "" for key, value in attrs}
        self._current = {
            "type": attributes.get("type", ""),
            "src": attributes.get("src", ""),
        }
        self._parts = []

    def handle_data(self, data):
        if self._current is not None:
            self._parts.append(data)

    def handle_endtag(self, tag):
        if tag.lower() != "script" or self._current is None:
            return
        self._current["code"] = "".join(self._parts).strip()
        self.scripts.append(self._current)
        self._current = None


def score_script(code):
    score = 0
    if re.search(r"\(function\s*\(", code) or re.search(r"\(\s*function\s*\(", code):
        score += 2
    if re.search(r"""\[\s*(['"`][^'"`]{1,80}['"`]\s*,\s*){8,}""", code):
        score += 4
    if re.search(r"\\x[0-9a-fA-F]{2}", code):
        score += 3
    if re.search(r"\\u[0-9a-fA-F]{4}", code):
        score += 1
    if re.search(r"fromCharCode|atob\s*\(|eval\s*\(", code):
        score += 4
    if re.search(r"_0x[0-9a-fA-F]{2,}", code):
        score += 5
    if len(code) > 2000:
        score += 2
    if len(code) > 8000:
        score += 2
    return score


def main():
    input_file = next((name for name in INPUT_CANDIDATES if Path(name).exists()), None)
    if not input_file:
        print("No HTML file found. Expected challenge.html or challenge_response.html.", file=sys.stderr)
        raise SystemExit(1)

    page = Path(input_file).read_text(encoding="utf-8")
    parser = ScriptParser()
    parser.feed(page)

    inline = []
    for index, script in enumerate(parser.scripts):
        code = script["code"]
        if not code or script["src"]:
            continue
        inline.append(
            {
                "index": index,
                "type": script["type"],
                "src": script["src"],
                "code": code,
                "score": score_script(code),
            }
        )

    if not inline:
        print("No inline script tags found in", input_file, file=sys.stderr)
        raise SystemExit(1)

    inline.sort(key=lambda script: (-script["score"], -len(script["code"])))
    chosen = inline[0]
    OUTPUT_FILE.write_text(chosen["code"], encoding="utf-8")

    print("Input:", input_file)
    print("Inline scripts:", len(inline))
    print(
        "Selected script index:",
        chosen["index"],
        "type:",
        chosen["type"] or "(none)",
        "length:",
        len(chosen["code"]),
        "score:",
        chosen["score"],
    )
    print("Wrote", OUTPUT_FILE)
    print("Top candidates:")
    for script in inline[:5]:
        preview = re.sub(r"\s+", " ", script["code"])[:80]
        print(f"- index {script['index']} score {script['score']} length {len(script['code'])}: {preview}")


if __name__ == "__main__":
    main()

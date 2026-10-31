"""Throwaway mechanical part of the STRATUM 10 code move: one TalkSlide class -> chapters/<slug>.py with
`def construct(talk)`. Class helper methods become module functions taking `talk`; the result is then hand-edited."""

import json
import re
import sys
import textwrap
from pathlib import Path

HERE = Path(__file__).parent
CLASS = re.compile(r"^class (\w+)\(TalkSlide\):\n", re.M)


def move(talk: Path, module: str) -> None:
    id_to_slug = json.loads((HERE / "id_to_slug.json").read_text())
    src = (talk / f"{module}.py").read_text()
    parts = CLASS.split(src)
    header, classes = parts[0], list(zip(parts[1::2], parts[2::2]))
    header = "\n".join(line for line in header.split("\n") if not line.startswith("from manim_presenters"))
    header = re.sub(r"^from \.(\w+) import", r"from helpers.\1 import", header, flags=re.M)
    for name, body in classes:
        chapter_id = re.search(r'chapter_id = "(\d\d)"', body)[1]
        body = re.sub(r'^    chapter_id = "\d\d"\n\n?', "", body, flags=re.M)
        body = re.sub(r"^\s*content = Transcript\.load\(.*\n", "", body, flags=re.M)
        methods = [m for m in re.findall(r"^    def (\w+)\(self", body, re.M) if m != "construct"]
        body = textwrap.dedent(body)
        body = re.sub(r"\bself\.presentation_path\b", "talk.root", body)
        body = re.sub(r'\bself\.beat\(("[\d.]+"), loop=True\)', r"talk.loop(\1)", body)
        for m in methods:
            body = re.sub(rf"\bself\.{m}\(", f"{m}(talk, ", body)
        body = re.sub(r"\(self, ", "(talk, ", body)
        body = re.sub(r"\(self\)", "(talk)", body)
        body = re.sub(r"\bself\b", "talk", body)
        uses_content = "content[" in body
        out = header.rstrip() + "\n"
        if uses_content:
            out += "from helpers.content import content\n"
        out += "\n\n" + body.strip() + "\n"
        dest = talk / "chapters" / f"{id_to_slug[chapter_id]}.py"
        dest.write_text(out)
        print(name, "->", dest.name, "methods:", methods)


if __name__ == "__main__":
    move(Path(sys.argv[1]), sys.argv[2])

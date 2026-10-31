"""Throwaway STRATUM 10 converter: transcript.json -> script.md + helpers/content.py + id_to_slug.json.
`convert.py convert TALK` writes the three; `convert.py rewrite TALK FILE...` rewrites quoted beat IDs in moved
chapter files through id_to_slug.json and fails on any ID it cannot map."""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
ID = re.compile(r"""(["'])(\d\d\.\d+)\1""")


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def convert(talk: Path) -> None:
    t = json.loads((talk / "transcript.json").read_text())
    seen: set[str] = set()
    id_to_slug: dict[str, str] = {}

    def unique(title: str, what: str) -> str:
        base = slug = slugify(title)
        n = 2
        while slug in seen:
            slug = f"{base}-{n}"
            n += 1
        if slug != base:
            print(f"renamed {what} {title!r}: {base} -> {slug}")
        seen.add(slug)
        return slug

    lines = [t["title"], ""]
    content = []
    for chapter in t["slides"]:
        cslug = unique(chapter["title"], f"chapter {chapter['id']}")
        id_to_slug[chapter["id"]] = cslug
        lines += [f"# {cslug}: {chapter['title']}", ""]
        for c in chapter["checkpoints"]:
            slug = unique(c["title"], f"beat {c['id']}")
            id_to_slug[c["id"]] = slug
            lines += [f"## {slug}: {c['title']}", "", c["narration"].strip()]
            if c.get("notes"):
                lines += [""] + [f"> {n}" if n.strip() else ">" for n in c["notes"].strip().split("\n")]
            lines.append("")
            fields = {k: c[k] for k in ("screen", "code", "asset") if k in c}
            content.append(f"    {slug!r}: Checkpoint({slug!r}, " + ", ".join(f"{k}={v!r}" for k, v in fields.items()) + "),")
    (talk / "script.md").write_text("\n".join(lines))
    (talk / "helpers" / "content.py").write_text(
        '"""The on-screen strings, code and asset of each beat, keyed by beat slug."""\n\n'
        "from typing import NamedTuple\n\n\n"
        "class Checkpoint(NamedTuple):\n"
        "    id: str\n"
        "    screen: list[str]\n"
        "    code: str | None = None\n"
        "    asset: str | None = None\n\n\n"
        "content = {\n" + "\n".join(content) + "\n}\n"
    )
    (HERE / "id_to_slug.json").write_text(json.dumps(id_to_slug, indent=1))
    print(json.dumps(id_to_slug))


def rewrite(files: list[Path]) -> None:
    id_to_slug = json.loads((HERE / "id_to_slug.json").read_text())
    for f in files:
        text = f.read_text()
        unknown = [m[2] for m in ID.finditer(text) if m[2] not in id_to_slug]
        assert not unknown, f"{f}: unmapped IDs {unknown}"
        f.write_text(ID.sub(lambda m: f'"{id_to_slug[m[2]]}"', text))


if __name__ == "__main__":
    cmd, talk, *rest = sys.argv[1:]
    convert(Path(talk)) if cmd == "convert" else rewrite([Path(p) for p in rest])

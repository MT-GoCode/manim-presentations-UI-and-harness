"""script.md: line 1 is the talk title; `# chapter-slug[: Title]` and `## beat-slug[: Title]` headings; text under a
beat is spoken, and its lines starting with `> ` are private notes. The slug is the stable identity of a chapter or
beat; the title is what people see (the slug when there is none)."""

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from markdown_it import MarkdownIt

SLUG = re.compile(r"[a-z0-9-]+")
HEADING = re.compile(r"(?P<slug>[^:]+?)(?::\s*(?P<title>.+?))?\s*")

Structure = tuple[tuple[str, str | None, tuple[tuple[str, str | None], ...]], ...]


@dataclass(frozen=True)
class Beat:
    slug: str
    title: str | None
    line: int  # 1-based line of the `##` heading
    start: int  # character span of the beat text in the file (surrounding blank lines excluded)
    end: int
    text: str

    @property
    def narration(self) -> str:
        """What is spoken: the text without its `> ` note lines."""
        return "\n".join(line for line in self.text.split("\n") if not _is_note(line)).strip("\n")

    @property
    def notes(self) -> str:
        return "\n".join(line[2:] for line in self.text.split("\n") if _is_note(line))


@dataclass(frozen=True)
class Chapter:
    slug: str
    title: str | None
    line: int
    beats: tuple[Beat, ...]


@dataclass(frozen=True)
class Script:
    title: str
    chapters: tuple[Chapter, ...]

    @property
    def structure(self) -> Structure:
        """What the build pairs with the chapters and what a title edit changes: slugs and titles, in order."""
        return tuple((c.slug, c.title, tuple((b.slug, b.title) for b in c.beats)) for c in self.chapters)

    def beat(self, slug: str) -> Beat:
        found = next((b for c in self.chapters for b in c.beats if b.slug == slug), None)
        if found is None:
            raise ValueError(f"beat {slug!r} not in script.md")
        return found


def _is_note(line: str) -> bool:
    return line.startswith("> ") or line == ">"


def _heading(content: str, line: int) -> tuple[str, str | None]:
    m = HEADING.fullmatch(content)
    assert m is not None  # the pattern accepts any non-empty heading without a leading colon
    slug, title = m["slug"].strip(), m["title"]
    if not SLUG.fullmatch(slug):
        raise ValueError(f"script.md:{line} bad slug {slug!r} (use a-z, 0-9, -; then an optional `: Title`)")
    return slug, title


def parse(text: str) -> Script:
    lines = text.split("\n")  # markdown-it counts lines on \n only; str.splitlines also splits on U+2028 and form feed
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line) + 1)
    tokens = MarkdownIt().parse(text)
    heads: list[tuple[int, str, str | None, int, int]] = []  # (level, slug, title, first line, line after heading)
    for i, token in enumerate(tokens):
        if token.type == "heading_open" and token.level == 0 and token.tag in ("h1", "h2") and token.map:
            first, after = token.map
            heads.append((int(token.tag[1]), *_heading(tokens[i + 1].content, first + 1), first, after))
    seen: set[str] = set()
    for _, slug, _, first, _ in heads:
        if slug in seen:
            raise ValueError(f"script.md:{first + 1} duplicate slug {slug!r}")
        seen.add(slug)
    title_end = heads[0][3] if heads else len(lines)
    title = next((line.strip() for line in lines[:title_end] if line.strip()), "")
    if not title or title.startswith("#"):
        raise ValueError("script.md: first line must be the talk title")
    chapters: list[tuple[str, str | None, int, list[Beat]]] = []
    for n, (level, slug, heading_title, first, after) in enumerate(heads):
        if level == 1:
            chapters.append((slug, heading_title, first + 1, []))
            continue
        if not chapters:
            raise ValueError(f"script.md:{first + 1} beat {slug!r} is before any `# chapter`")
        stop = heads[n + 1][3] if n + 1 < len(heads) else len(lines)
        region = text[offsets[after] : offsets[stop]]
        body = region.strip("\n")
        start = offsets[after] + (len(region) - len(region.lstrip("\n")) if body else min(1, len(region)))
        chapters[-1][3].append(Beat(slug, heading_title, first + 1, start, start + len(body), body))
    return Script(title, tuple(Chapter(s, t, line, tuple(b)) for s, t, line, b in chapters))


def load(path: Path) -> Script:
    return parse(Path(path).read_text(encoding="utf-8"))


def _splice(current: str, beat_slug: str, text: str) -> str:
    """current with one beat's text replaced; refuses any change to the headings (slugs or titles)."""
    before = parse(current)
    beat = before.beat(beat_slug)
    tail = current[beat.end :]
    if beat.start == beat.end and tail:
        text += "\n\n"
    updated = current[: beat.start] + text + tail
    try:
        after = parse(updated).structure
    except ValueError:
        after = None
    if after != before.structure:
        raise ValueError("headings belong in script.md, not in beat text")
    return updated


def save_beat(path: Path, beat_slug: str, text: str) -> None:
    """Replace one beat's text in the file as it is on disk at this call, so another writer's edit to any other beat
    survives; the read and the atomic replace are microseconds apart (two writers on one beat: the last one wins)."""
    path = Path(path)
    updated = _splice(path.read_text(encoding="utf-8"), beat_slug, text)
    descriptor, name = tempfile.mkstemp(prefix=".script.", dir=path.parent)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
        stream.write(updated)
    os.replace(name, path)

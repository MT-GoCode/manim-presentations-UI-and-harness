"""mpres: one root, one subcommand per job, each taking a talk folder path. The path is validated once, here; every
module after this boundary trusts it. Subcommand modules are imported only when their command runs, so `--help` and
`present` never import Manim."""

import argparse
import os
import sys
from pathlib import Path

SUFFIX = ".manim-presentation"


class BoundaryError(Exception):
    pass


def talk_root(arg: str) -> Path:
    """The talk folder named by `arg`, or BoundaryError saying exactly what is wrong with it."""
    root = Path(arg).expanduser().resolve()
    if root.suffix != SUFFIX:
        raise BoundaryError(f"{root}: a talk folder's name ends in {SUFFIX}")
    if not root.is_dir():
        raise BoundaryError(f"{root}: no such folder")
    if "script.md" not in {p.name for p in root.iterdir()}:  # exact case: APFS would also open SCRIPT.md
        raise BoundaryError(f"{root}: no script.md (exactly that name, lowercase)")
    if (root / "manim.cfg").exists():
        raise BoundaryError(f"{root}/manim.cfg: Manim would read it from the working directory; use talk.toml")
    return root


def positive(text: str) -> int:
    n = int(text)
    if n < 1:
        raise argparse.ArgumentTypeError(f"{n}: at least 1")
    return n


def run_build(root: Path, args: argparse.Namespace) -> int:
    from manim_presentations.build import BuildError, build

    try:
        return build(root, args.workers)
    except BuildError as e:
        print("\n".join(e.lines), file=sys.stderr)
        return e.code


def run_shots(root: Path, args: argparse.Namespace) -> int:
    from manim_presentations.deck import IncompatibleBuild, Stale
    from manim_presentations.headroom import TooBig
    from manim_presentations.shots import ShotsError, shots

    try:
        return shots(root, args.out and Path(args.out).expanduser().resolve(), args.workers)
    except (IncompatibleBuild, Stale, ShotsError, TooBig) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def even(text: str) -> int:
    n = positive(text)
    if n % 2:
        raise argparse.ArgumentTypeError(f"{n}: H.264 yuv420p needs an even height")
    return n


def crf(text: str) -> int:
    n = int(text)
    if not 0 <= n <= 51:
        raise argparse.ArgumentTypeError(f"{n}: x264 takes 0-51")
    return n


def html_out(text: str) -> Path:
    out = Path(text).expanduser().resolve()
    if not out.parent.is_dir():
        raise argparse.ArgumentTypeError(f"{out.parent}: no such folder")
    if out.is_dir():
        raise argparse.ArgumentTypeError(f"{out} is a folder; name the .html file to write")
    return out


def run_export(root: Path, args: argparse.Namespace) -> int:
    from manim_presentations.deck import IncompatibleBuild, Stale
    from manim_presentations.export import ExportError, export
    from manim_presentations.headroom import TooBig

    try:
        return export(root, args.out, args.height, args.crf, args.transcript, args.workers)
    except (IncompatibleBuild, Stale, ExportError, TooBig) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mpres", description="Build, present, screenshot and export Manim talks.")
    sub = p.add_subparsers(dest="command", metavar="command")
    workers = "run exactly N jobs at once (default: 75%% of free headroom)"
    b = sub.add_parser("build", help="check the talk and render what changed")
    b.add_argument("talk", help="path to a <name>.manim-presentation folder")
    b.add_argument("--workers", type=positive, metavar="N", help=workers)
    b.set_defaults(run=run_build)
    s = sub.add_parser("shots", help="first, middle and last frame of every beat, and a contact sheet per chapter")
    s.add_argument("talk", help="path to a <name>.manim-presentation folder")
    s.add_argument("--out", metavar="DIR", help="output folder (default: /tmp/mpres-shots/<talk>-<hash>/)")
    s.add_argument("--workers", type=positive, metavar="N", help=workers)
    s.set_defaults(run=run_shots)
    e = sub.add_parser("export", help="the talk as one self-contained HTML file that plays offline")
    e.add_argument("talk", help="path to a <name>.manim-presentation folder")
    e.add_argument("--out", required=True, type=html_out, metavar="FILE.html", help="where to write the page")
    e.add_argument("--height", type=even, metavar="H", help="video height (default: min(1080, the source height))")
    e.add_argument(
        "--crf", type=crf, metavar="C", help="x264 quality, 0-51, lower is better (default: measured, printed)"
    )
    e.add_argument(
        "--transcript",
        choices=("none", "narration", "full"),
        default="none",
        help="none: no text of the script; narration: what is spoken; full: plus the private > notes (default: none)",
    )
    e.add_argument("--workers", type=positive, metavar="N", help=workers)
    e.set_defaults(run=run_export)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command is None:
        parser().print_help()
        return 2
    try:
        root = talk_root(args.talk)
    except BoundaryError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    os.chdir(root)  # the build parent imports Manim, which reads ./manim.cfg; the boundary proved there is none here
    return args.run(root, args)


if __name__ == "__main__":
    sys.exit(main())

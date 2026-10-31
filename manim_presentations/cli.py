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


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mpres", description="Build, present, screenshot and export Manim talks.")
    sub = p.add_subparsers(dest="command", metavar="command")
    b = sub.add_parser("build", help="check the talk and render what changed")
    b.add_argument("talk", help="path to a <name>.manim-presentation folder")
    b.add_argument(
        "--workers", type=positive, metavar="N", help="run exactly N jobs at once (default: 75%% of free headroom)"
    )
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
    if args.command == "build":
        from manim_presentations.build import BuildError, build

        try:
            return build(root, args.workers)
        except BuildError as e:
            print("\n".join(e.lines), file=sys.stderr)
            return e.code
    raise AssertionError(args.command)


if __name__ == "__main__":
    sys.exit(main())

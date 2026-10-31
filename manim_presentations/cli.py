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


def run_present(root: Path, args: argparse.Namespace) -> int:
    from manim_presentations.deck import Busy, IncompatibleBuild, Stale
    from manim_presentations.presenter import UnknownBeat, present

    try:
        return present(root, args.start)
    except UnknownBeat as e:
        slug, slugs = e.args
        print(f"error: --from {slug}: no such beat; the beats are: {' '.join(slugs)}", file=sys.stderr)
        return 2
    except Busy:
        print(f"error: {root} is already being presented", file=sys.stderr)
        return 3
    except (IncompatibleBuild, Stale) as e:
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
    pr = sub.add_parser("present", help="present the built talk: a Presenter View and an Audience View to share")
    pr.add_argument("talk", help="path to a <name>.manim-presentation folder")
    pr.add_argument("--from", dest="start", metavar="BEAT", help="start just before this beat (its slug)")
    pr.set_defaults(run=run_present)
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

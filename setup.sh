#!/usr/bin/env bash
# The only install path, idempotent: Homebrew deps, repo-local TinyTeX, the uv env, and `mpres` on PATH.
#   ./setup.sh          install
#   ./setup.sh --dev    also the test browsers (Playwright WebKit; Google Chrome must be installed)
set -euo pipefail
echo "setup: the first run takes several minutes (TinyTeX download). Agents: run it detached or with a long timeout;"
echo "       re-running is safe and fast."
cd "$(dirname "$0")"
REPO=$PWD
DEV=0
case "${1:-}" in
  "") ;;
  --dev) DEV=1 ;;
  *) echo "setup: unknown argument $1 (usage: ./setup.sh [--dev])" >&2; exit 2 ;;
esac
N=7
phase() { echo "phase $1/$N: $2"; }

phase 1 "Homebrew"
command -v brew >/dev/null || { echo "setup: Homebrew is required: https://brew.sh" >&2; exit 1; }
BREW=$(brew --prefix)

phase 2 "cairo, pkg-config, uv"  # pycairo has no macOS wheels; uv from brew lands where Homebrew's shellenv keeps PATH
for pkg in cairo pkg-config uv; do brew list --versions "$pkg" >/dev/null || brew install "$pkg"; done
export PATH="$BREW/bin:$PATH"

phase 3 "TinyTeX (repo-local)"
TINYTEX_VERSION=2026.10  # the installer bundle; packages come from the current repository (the TeX/text cache is
#                         keyed on the installed package database, so any change shows up as a new cache)
TEX="$REPO/.tinytex/TinyTeX"
if ! ls "$TEX"/bin/*/tlmgr >/dev/null 2>&1; then
  mkdir -p .tinytex
  curl -sL https://yihui.org/tinytex/install-bin-unix.sh |
    TINYTEX_DIR="$REPO/.tinytex" TINYTEX_VERSION="$TINYTEX_VERSION" sh -s - "" --no-path
  "$(dirname "$(ls "$TEX"/bin/*/tlmgr)")/tlmgr" update --self  # a bundle can lag the repository; tlmgr refuses
fi                                                              # installs until it is current
BIN=$(dirname "$(ls "$TEX"/bin/*/tlmgr)")
# The packages Manim's default TeX template and MathTex need (Manim docs' TinyTeX list, minus the CJK set). Run every
# time: a no-op when present, and it completes an install a failed run left half done.
"$BIN/tlmgr" install amsmath babel-english cbfonts-fd cm-super count1to doublestroke dvisvgm everysel fontspec \
  frcursive fundus-calligra gnu-freefont jknapltx latex-bin mathastext microtype multitoc physics preview \
  prelim2e ragged2e relsize rsfs setspace standalone tipa wasy wasysym xcolor xetex xkeyval >/dev/null
echo "$BIN" > .tinytex/bin-path

phase 4 "Python environment"
if [ "$DEV" = 1 ]; then
  PKG_CONFIG_PATH="$BREW/lib/pkgconfig" uv sync --compile-bytecode
  uv run playwright install webkit  # never `playwright install chrome`: it reinstalls /Applications/Google Chrome.app
  [ -d "/Applications/Google Chrome.app" ] || { echo "setup --dev: Google Chrome is required for export tests" >&2; exit 1; }
else
  PKG_CONFIG_PATH="$BREW/lib/pkgconfig" uv sync --compile-bytecode --no-dev
fi

phase 5 "mpres on PATH"
LINK="$HOME/.local/bin/mpres"
mkdir -p "$HOME/.local/bin"
FOUND=$(command -v mpres || true)
if [ -n "$FOUND" ] && [ "$FOUND" != "$LINK" ]; then
  echo "setup: \`mpres\` resolves to $FOUND, which shadows $LINK; remove it or reorder PATH" >&2
  exit 1
fi
OLD=$(readlink "$LINK" || true)
if [ "$OLD" != "$REPO/bin/mpres" ]; then
  ln -sfn "$REPO/bin/mpres" "$LINK"
  [ -n "$OLD" ] && echo "setup: relinked $LINK: $OLD -> $REPO/bin/mpres"
fi
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *)
    case "${SHELL:-}" in
      */zsh) RC="${ZDOTDIR:-$HOME}/.zshrc" ;;
      *) RC="$HOME/.bash_profile" ;;
    esac
    LINE='export PATH="$HOME/.local/bin:$PATH"'
    if ! grep -qxF "$LINE" "$RC" 2>/dev/null; then
      echo "$LINE" >> "$RC"
      echo "setup: added ~/.local/bin to PATH in $RC (open a new shell, or call $LINK)"
    fi
    ;;
esac

phase 6 "check"
"$LINK" --help >/dev/null

phase 7 "example build"  # in a temporary folder, so no build/ appears in the repo
EXAMPLE=$(mktemp -d)/hello.manim-presentation
cp -R "$REPO/examples/hello.manim-presentation" "$EXAMPLE"
"$LINK" build "$EXAMPLE" | tail -1
rm -rf "$(dirname "$EXAMPLE")"
echo "setup OK: mpres -> $REPO/bin/mpres; TeX at $(cat .tinytex/bin-path)"

#!/bin/bash
# STRATUM 11's first-contact check (PLAN §9 deliverable 10, P8's route): the README's exact prompt, run by the real
# Claude binary in a fresh clone, as a new user's machine would see it. Usage: run.sh <branch>
set -euo pipefail
branch=${1:?usage: run.sh <branch>}
here=$(cd "$(dirname "$0")" && pwd)
work=$(mktemp -d /tmp/mpres-first-contact.XXXXXX)
mkdir "$work/zdotdir"  # a throwaway shell rc: setup's PATH handling runs without touching the user's
cd "$work"
git clone -q -b "$branch" https://github.com/MT-GoCode/manim-presentations-UI-and-harness.git
claude=$(ls -d "$HOME"/.local/share/claude/versions/* | sort -V | tail -1)  # the real binary, not a wrapper
stripped=$(printf %s "$PATH" | tr : '\n' | grep -vx "$HOME/.local/bin" | paste -sd: -)
echo "first-contact: $claude in $work, branch $branch"
env PATH="$stripped" ZDOTDIR="$work/zdotdir" "$claude" --setting-sources project --strict-mcp-config \
  --permission-mode bypassPermissions --output-format stream-json --verbose \
  -p "$(cat "$here/prompt.txt")" > "$work/transcript.jsonl"
python3 - "$work/transcript.jsonl" "$here/first-contact.md" "$branch" <<'PY'
import json, sys
transcript, out, branch = sys.argv[1:]
events = [json.loads(line) for line in open(transcript)]
answer = next(e["result"] for e in reversed(events) if e.get("type") == "result")
text = json.dumps(events)
built = "phase 7/7: example build" in text and "built /" in text
words = len(answer.split())
open(out, "w").write(
    f"# First contact ({branch})\n\nSetup's example build succeeded: {built}. Answer: {words} words.\n\n{answer}\n"
)
print(f"example build: {built}; answer: {words} words")
sys.exit(0 if built and words < 150 else 1)
PY

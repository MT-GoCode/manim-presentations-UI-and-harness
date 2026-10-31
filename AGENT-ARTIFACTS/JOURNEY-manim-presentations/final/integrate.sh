#!/bin/bash
# The last step of the journey: main from the final reviewed commit, made the default; probe/p5 and its runs deleted
# (DECISIONS: P5 probe workflow); the merged stage branches deleted. Usage: integrate.sh <commit on join>
set -euo pipefail
commit=${1:?usage: integrate.sh <commit>}
repo=MT-GoCode/manim-presentations-UI-and-harness
clone=/Users/minhtrinh/general-purpose/conversation-contexts/manim-presentations-harness/manim-presentations-UI-and-harness
eval "$(gitas use personal)"
cd "$clone"
git fetch -q origin
git merge-base --is-ancestor "$commit" origin/join  # the commit must be on the reviewed line
git push -q origin "$commit:refs/heads/main"
gitas exec personal -- gh repo edit "$repo" --default-branch main
git checkout -q -B main origin/main
git branch --set-upstream-to=origin/main main >/dev/null
for run in $(gitas exec personal -- gh run list -R "$repo" --branch probe/p5 --limit 100 --json databaseId -q '.[].databaseId'); do
  gitas exec personal -- gh run delete -R "$repo" "$run"
done
for branch in probe/p5 wip s3 s4 s6 s7 s8 s9 sj/export ci-time join; do
  git merge-base --is-ancestor "origin/$branch" origin/main || [ "$branch" = probe/p5 ] || { echo "not merged: $branch"; exit 1; }
  git push -q origin --delete "$branch"
done
git remote prune origin
echo "main = $(git rev-parse --short origin/main), default branch: $(gitas exec personal -- gh repo view $repo --json defaultBranchRef -q .defaultBranchRef.name)"

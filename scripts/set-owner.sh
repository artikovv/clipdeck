#!/usr/bin/env bash
# One-time setup: put your GitHub username and email into every file.
#   scripts/set-owner.sh <github-username> <email>
# Flatpak app IDs can't contain "-", so a username like "farroukh-a" becomes
# "farroukh_a" in the app ID (io.github.farroukh_a.Clipdeck) but stays as-is in URLs.
set -euo pipefail
[[ $# -eq 2 ]] || { echo "usage: $0 <github-username> <email>"; exit 1; }
user="$1"; email="$2"; idpart="${user//-/_}"
cd "$(dirname "$0")/.."
grep -q 'GHUSER' clipdeck/__init__.py || { echo "Already set up."; exit 0; }

files=$(grep -rlI --exclude-dir=.git --exclude=set-owner.sh -e GHUSER -e GHEMAIL .)
# App IDs first (with underscores), then URLs and everything else.
sed -i -e "s/io\.github\.GHUSER/io.github.${idpart}/g" -e "s/GHUSER/${user}/g" -e "s/GHEMAIL/${email}/g" $files
for f in $(git ls-files | grep GHUSER); do
    git mv "$f" "${f//GHUSER/$idpart}"
done
echo "Done. App ID is now io.github.${idpart}.Clipdeck. Review with 'git diff', then commit."

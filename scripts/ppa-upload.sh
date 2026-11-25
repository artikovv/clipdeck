#!/usr/bin/env bash
# Builds the current release as a signed source package and uploads it to the PPA.
#   scripts/ppa-upload.sh            # Ubuntu 24.04 / Linux Mint 22 (noble)
#   scripts/ppa-upload.sh jammy      # another Ubuntu release
# Set DRY_RUN=1 to build without signing or uploading.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERIES="${1:-noble}"
PPA="${PPA:-ppa:farroukh/clipdeck}"
WORK="$HOME/ppa"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/clipdeck/__init__.py")"
EMAIL="$(sed -n 's/^Maintainer: .*<\(.*\)>/\1/p' "$ROOT/debian/control")"
NAME="Farroukh Artikov"
DEBVER="$VERSION-1~${SERIES}1"

step() { printf '\n==> %s\n' "$*"; }
fail() { printf '\nError: %s\n' "$*" >&2; exit 1; }

step "Clipdeck $VERSION for $SERIES (package version $DEBVER)"
git -C "$ROOT" rev-parse -q --verify "refs/tags/v$VERSION" >/dev/null \
    || fail "there's no v$VERSION tag. Release the version first (scripts/bump-version.sh, commit, tag)."
[[ -n "$EMAIL" ]] || fail "couldn't read your email from debian/control."

step "Preparing the source in $WORK"
mkdir -p "$WORK"
cd "$WORK"
rm -rf "clipdeck-$VERSION"
rm -f "clipdeck_${VERSION}-1"*          # leftovers from earlier attempts at this version
if [[ ! -f "clipdeck_$VERSION.orig.tar.gz" ]]; then
    git -C "$ROOT" archive --prefix="clipdeck-$VERSION/" -o "$WORK/clipdeck_$VERSION.orig.tar.gz" "v$VERSION"
fi
tar xf "clipdeck_$VERSION.orig.tar.gz"
cd "clipdeck-$VERSION"

step "Marking it for $SERIES"
{ printf 'clipdeck (%s) %s; urgency=medium\n\n  * Build for Ubuntu %s.\n\n -- %s <%s>  %s\n\n' \
    "$DEBVER" "$SERIES" "$SERIES" "$NAME" "$EMAIL" "$(LC_ALL=C date -R)"
  cat debian/changelog; } > debian/changelog.new
mv debian/changelog.new debian/changelog
head -1 debian/changelog | grep -q "($DEBVER) $SERIES;" || fail "the changelog entry wasn't added."
head -1 debian/changelog

if [[ "${DRY_RUN:-0}" == 1 ]]; then
    step "Building without signing (DRY_RUN)"
    debuild -S -sa -us -uc
    echo "Built $WORK/clipdeck_${DEBVER}_source.changes (not signed, not uploaded)."
    exit 0
fi

FPR="$(gpg --list-secret-keys --with-colons | awk -F: '/^fpr/ {print $10; exit}')"
[[ -n "$FPR" ]] || fail "no GPG key found. Create one first (gpg --full-generate-key)."

step "Building and signing. Enter your GPG key passphrase when asked."
echo "Tip: switch the keyboard layout to English first, and check Caps Lock."
debuild -S -sa -k"$FPR"

step "Uploading to $PPA"
cd "$WORK"
dput "$PPA" "clipdeck_${DEBVER}_source.changes"

step "Done"
echo "Launchpad emails you when it accepts the upload, and again when the build finishes."
echo "Follow it at: https://launchpad.net/~${PPA#ppa:}" | sed 's|/clipdeck$|/+archive/ubuntu/clipdeck|'

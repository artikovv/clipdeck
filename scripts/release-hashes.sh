#!/usr/bin/env bash
# After pushing a tag, prints the source tarball hash and fills it into the
# Arch PKGBUILD. Paste the same hash into the Flathub manifest.
#   scripts/release-hashes.sh 0.2.0
set -euo pipefail
cd "$(dirname "$0")/.."
version="${1:?usage: $0 <version>}"
url="$(sed -n 's/^url="\(.*\)"/\1/p' packaging/arch/PKGBUILD)/archive/v$version.tar.gz"
sha="$(curl -fsSL "$url" | sha256sum | cut -d' ' -f1)"
sed -i "s/^sha256sums=.*/sha256sums=('$sha')/" packaging/arch/PKGBUILD
echo "$url"
echo "sha256: $sha"

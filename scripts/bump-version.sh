#!/usr/bin/env bash
# Sets a new version everywhere it appears.
#   scripts/bump-version.sh 0.3.0 "Short summary of the release"
set -euo pipefail
[[ $# -ge 1 ]] || { echo "usage: $0 <version> [summary]"; exit 1; }
new="$1"; summary="${2:-New release.}"
cd "$(dirname "$0")/.."
old="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' clipdeck/__init__.py)"
today="$(date +%Y-%m-%d)"
appid="$(sed -n 's/^APP_ID = "\(.*\)"/\1/p' clipdeck/__init__.py)"
email="$(sed -n 's/^Maintainer: .*<\(.*\)>/\1/p' debian/control)"

sed -i "s/^__version__ = \".*\"/__version__ = \"$new\"/" clipdeck/__init__.py
sed -i "s/^version: '.*'/version: '$new'/" snap/snapcraft.yaml
sed -i "s/^pkgver=.*/pkgver=$new/; s/^pkgrel=.*/pkgrel=1/" packaging/arch/PKGBUILD
sed -i "s/^Version: .*/Version:        $new/; s/^Release: .*/Release:        1%{?dist}/" packaging/rpm/clipdeck.spec
sed -i "/^%changelog/a * $(LC_ALL=C date '+%a %b %d %Y') Farroukh Artikov <$email> - $new-1\n- $summary\n" packaging/rpm/clipdeck.spec
sed -i "s/Clipdeck $old/Clipdeck $new/" docs/clipdeck.1
sed -i "s/^Version $old/Version $new/" README.md
sed -i "s|  <releases>|  <releases>\n    <release version=\"$new\" date=\"$today\">\n      <description><p>$summary</p></description>\n    </release>|" "data/$appid.metainfo.xml"
{ printf 'clipdeck (%s-1) unstable; urgency=medium\n\n  * %s\n\n -- Farroukh Artikov <%s>  %s\n\n' \
    "$new" "$summary" "$email" "$(LC_ALL=C date -R)"; cat debian/changelog; } > debian/changelog.new
mv debian/changelog.new debian/changelog
# Release the "Unreleased" notes under the new version, and start a fresh "Unreleased" section.
sed -i "s/^## Unreleased/## Unreleased\n\n## $new ($today)/" CHANGELOG.md

echo "Version $old -> $new. Review with 'git diff', then:"
echo "  git commit -am 'Release $new' && git tag v$new && git push && git push origin v$new"

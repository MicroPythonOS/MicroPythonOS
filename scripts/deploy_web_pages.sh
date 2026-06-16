#!/bin/bash
# Build the MicroPythonOS web export and publish it to a GitHub Pages branch.
#
# This builds web/ (unless --no-build) and force-pushes its contents as a single
# commit to the `gh-pages` branch of the chosen remote. GitHub Pages then serves
# it at https://<owner>.github.io/<repo>/.
#
# One-time setup (in the repo's GitHub settings):
#   Settings → Pages → Build and deployment → Source: "Deploy from a branch",
#   Branch: gh-pages / (root).
#
# Usage:
#   scripts/deploy_web_pages.sh                 # build, then deploy to `fork`
#   scripts/deploy_web_pages.sh --no-build      # deploy the existing web/ as-is
#   REMOTE=origin scripts/deploy_web_pages.sh   # deploy to a different remote
#   BRANCH=gh-pages scripts/deploy_web_pages.sh # use a different Pages branch

set -euo pipefail

mydir=$(cd "$(dirname "$0")" && pwd -P)
codebasedir=$(cd "$mydir/.." && pwd -P)

remote="${REMOTE:-fork}"
branch="${BRANCH:-gh-pages}"
webdir="$codebasedir/web"

# 1. Build unless told otherwise.
if [ "${1:-}" != "--no-build" ]; then
	"$mydir/build_mpos_web.sh"
fi

if [ ! -f "$webdir/index.html" ]; then
	echo "ERROR: $webdir/index.html not found. Build first (omit --no-build)."
	exit 1
fi

# 2. Validate the remote exists.
if ! git -C "$codebasedir" remote get-url "$remote" >/dev/null 2>&1; then
	echo "ERROR: git remote '$remote' not found. Add it or set REMOTE=<name>."
	echo "Available remotes:"
	git -C "$codebasedir" remote -v
	exit 1
fi
remote_url=$(git -C "$codebasedir" remote get-url "$remote")

# 3. Stage the built site in a temporary worktree and publish as a single
#    squashed commit (history is not needed for a generated artifact).
tmpdir=$(mktemp -d)
cleanup() { rm -rf "$tmpdir"; }
trap cleanup EXIT

cp -R "$webdir"/. "$tmpdir"/
# Jekyll would otherwise ignore files/dirs starting with "_" (e.g. the
# preloaded filesystem). Disable Jekyll processing on Pages.
touch "$tmpdir/.nojekyll"

short_sha=$(git -C "$codebasedir" rev-parse --short HEAD 2>/dev/null || echo "unknown")

git -C "$tmpdir" init -q
git -C "$tmpdir" checkout -q -b "$branch"
git -C "$tmpdir" add -A
git -C "$tmpdir" -c user.name="web-deploy" -c user.email="web-deploy@local" \
	commit -q -m "Deploy web export ($short_sha)"

echo "Force-pushing web export to $remote/$branch ($remote_url)..."
git -C "$tmpdir" push -f "$remote_url" "$branch":"$branch"

# 4. Print the resulting Pages URL when the remote is a GitHub repo.
if [[ "$remote_url" =~ github.com[:/]+([^/]+)/([^/.]+) ]]; then
	owner="${BASH_REMATCH[1]}"
	repo="${BASH_REMATCH[2]}"
	echo
	echo "Pushed. Once Pages is enabled (Settings → Pages → branch: $branch / root),"
	echo "the site will be live at:"
	echo "    https://${owner}.github.io/${repo}/"
fi

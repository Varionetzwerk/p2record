#!/usr/bin/env bash
# release.sh — tag, push to GitHub, update AUR
#
# Usage:
#   ./release.sh 0.3.0        # new release with version
#   ./release.sh              # bump patch (0.2.0 → 0.2.1)
#   ./release.sh --aur-only   # only push PKGBUILD to AUR (no new tag)
#
# First-time setup:
#   git remote add origin https://github.com/YOUR-USER/p2record.git
#   git remote add aur     ssh://aur@aur.archlinux.org/p2record-git.git

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PKGBUILD="$ROOT/python/PKGBUILD"
SRCINFO="$ROOT/python/.SRCINFO"

# ── colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}✓${RESET} $*"; }
info() { echo -e "${CYAN}→${RESET} $*"; }
warn() { echo -e "${YELLOW}!${RESET} $*"; }
die()  { echo -e "${RED}✗${RESET} $*" >&2; exit 1; }

# ── args ─────────────────────────────────────────────────────────────────────
AUR_ONLY=false
NEW_VERSION=""

for arg in "$@"; do
    case "$arg" in
        --aur-only) AUR_ONLY=true ;;
        [0-9]*.*) NEW_VERSION="$arg" ;;
        *) die "Unknown argument: $arg" ;;
    esac
done

cd "$ROOT"

# ── git sanity check ─────────────────────────────────────────────────────────
git rev-parse --git-dir &>/dev/null || die "Not a git repository. Run: git init"

if ! git remote get-url origin &>/dev/null; then
    die "No 'origin' remote. Run:\n  git remote add origin https://github.com/YOUR-USER/p2record.git"
fi

# ── aur-only shortcut ────────────────────────────────────────────────────────
if $AUR_ONLY; then
    push_aur
    exit 0
fi

# ── determine version ─────────────────────────────────────────────────────────
if [[ -z "$NEW_VERSION" ]]; then
    LAST=$(git tag --sort=-v:refname | grep -E '^v?[0-9]+\.[0-9]+\.[0-9]+$' | head -1)
    if [[ -z "$LAST" ]]; then
        NEW_VERSION="0.2.0"
        warn "No existing tags found — using $NEW_VERSION"
    else
        LAST_CLEAN="${LAST#v}"
        IFS='.' read -r MAJOR MINOR PATCH <<< "$LAST_CLEAN"
        PATCH=$((PATCH + 1))
        NEW_VERSION="$MAJOR.$MINOR.$PATCH"
        info "Last tag: $LAST  →  auto bump: $NEW_VERSION"
    fi
fi

TAG="v$NEW_VERSION"

# ── confirm ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}Release: $TAG${RESET}"
echo ""
echo "  Will do:"
echo "    1. Stage all changes & commit"
echo "    2. Create git tag $TAG"
echo "    3. Push to GitHub (origin)"
echo "    4. Regenerate .SRCINFO"
echo "    5. Push PKGBUILD + .SRCINFO to AUR (if remote 'aur' exists)"
echo ""
read -rp "Proceed? [y/N] " CONFIRM
[[ "${CONFIRM,,}" == "y" ]] || { echo "Aborted."; exit 0; }
echo ""

# ── stage & commit ────────────────────────────────────────────────────────────
if [[ -n "$(git status --porcelain)" ]]; then
    info "Staging all changes..."
    git add -A
    git commit -m "release $TAG"
    ok "Committed"
else
    info "Nothing to commit — working tree clean"
fi

# ── tag ───────────────────────────────────────────────────────────────────────
if git rev-parse "$TAG" &>/dev/null; then
    warn "Tag $TAG already exists — skipping tag creation"
else
    git tag "$TAG"
    ok "Tag $TAG created"
fi

# ── push to GitHub ────────────────────────────────────────────────────────────
info "Pushing to GitHub..."
git push origin main --tags
ok "GitHub up to date"

# ── regenerate .SRCINFO ───────────────────────────────────────────────────────
if command -v makepkg &>/dev/null; then
    info "Regenerating .SRCINFO..."
    (cd "$ROOT/python" && makepkg --printsrcinfo > .SRCINFO)
    ok ".SRCINFO updated"
else
    warn "makepkg not found — skipping .SRCINFO regeneration"
fi

# ── push to AUR ───────────────────────────────────────────────────────────────
push_aur() {
    if ! git remote get-url aur &>/dev/null; then
        warn "No 'aur' remote configured — skipping AUR push"
        echo ""
        echo "  To add AUR remote (after package is registered on aur.archlinux.org):"
        echo "  git remote add aur ssh://aur@aur.archlinux.org/p2record-git.git"
        echo ""
        echo "  GitHub: https://github.com/Varionetzwerk/p2record"
        return
    fi

    AUR_TMPDIR=$(mktemp -d)
    trap "rm -rf $AUR_TMPDIR" EXIT

    info "Preparing AUR push..."
    cp "$PKGBUILD" "$AUR_TMPDIR/PKGBUILD"
    cp "$SRCINFO"  "$AUR_TMPDIR/.SRCINFO"

    # Push only PKGBUILD + .SRCINFO to AUR remote (sparse approach)
    AUR_URL=$(git remote get-url aur)
    git clone "$AUR_URL" "$AUR_TMPDIR/aur-repo" 2>/dev/null || {
        mkdir -p "$AUR_TMPDIR/aur-repo"
        git -C "$AUR_TMPDIR/aur-repo" init
        git -C "$AUR_TMPDIR/aur-repo" remote add origin "$AUR_URL"
    }

    cp "$PKGBUILD" "$AUR_TMPDIR/aur-repo/PKGBUILD"
    cp "$SRCINFO"  "$AUR_TMPDIR/aur-repo/.SRCINFO"

    git -C "$AUR_TMPDIR/aur-repo" add PKGBUILD .SRCINFO
    if git -C "$AUR_TMPDIR/aur-repo" diff --cached --quiet; then
        warn "AUR: no changes in PKGBUILD/.SRCINFO"
    else
        git -C "$AUR_TMPDIR/aur-repo" commit -m "update to $TAG"
        git -C "$AUR_TMPDIR/aur-repo" push origin master
        ok "AUR updated"
    fi
}

push_aur

# ── done ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}Released $TAG successfully!${RESET}"
echo ""
echo "  GitHub: $(git remote get-url origin | sed 's/\.git$//')/releases/tag/$TAG"
echo "  yay:    yay -Syu  (users will see update automatically)"
echo ""

#!/bin/bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: delete_named_dirs.sh [--delete] ROOT NAME

Recursively find directories whose basename exactly equals NAME.
By default, only preview matches. Use --delete to remove them and their contents.
The root directory and same-name regular files are preserved.
ROOT is resolved to a physical path; nested symbolic links are not followed.
Run against a directory tree that is not being modified concurrently.

Examples:
    ./delete_named_dirs.sh "/path/to/project" "node_modules"
    ./delete_named_dirs.sh --delete "/path/to/project" "node_modules"
EOF
}

delete=false
case "${1:-}" in
    -h|--help)
        usage
        exit 0
        ;;
    --delete)
        delete=true
        shift
        ;;
esac

if [[ $# -ne 2 ]]; then
    usage >&2
    exit 2
fi

root=$1
name=$2
case "$name" in
    ''|.|..|*/*)
        printf 'Error: NAME must be a single, nonempty directory name other than . or ..\n' >&2
        exit 2
        ;;
esac

if [[ -z "$root" || ! -d "$root" ]]; then
    printf 'Error: ROOT is not a directory: %q\n' "$root" >&2
    exit 2
fi

# The trailing slash preserves trailing newlines through command substitution.
root_abs=$(CDPATH= cd -P -- "$root" && printf '%s/' "$PWD")
root_abs=${root_abs%/}
if [[ "$root_abs" == / ]]; then
    printf 'Error: refusing to scan the filesystem root.\n' >&2
    exit 2
fi

scan_file=$(mktemp "${TMPDIR:-/tmp}/delete_named_dirs.XXXXXX")
trap 'rm -f -- "$scan_file"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Complete the scan before deletion; visit nested matches before their parents.
if ! find -P "$root_abs" -depth -mindepth 1 -type d -print0 > "$scan_file"; then
    printf 'Error: scan failed; nothing was deleted.\n' >&2
    exit 1
fi

action='Would delete'
if [[ "$delete" == true ]]; then
    action='Deleted'
fi

count=0
while IFS= read -r -d '' path; do
    [[ "${path##*/}" == "$name" ]] || continue
    if [[ "$delete" == true ]]; then
        if [[ ! -d "$path" || -L "$path" ]]; then
            printf 'Skipped changed path: %q\n' "$path" >&2
            continue
        fi
        rm -rf -- "$path"
    fi
    printf '%s: %q\n' "$action" "$path"
    count=$((count + 1))
done < "$scan_file"

printf '%s: %d directory(s).\n' "$action" "$count"

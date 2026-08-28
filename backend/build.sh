#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

staging_dir="backend/.build-staging"
bundle_dir="fastread-frontend/src-tauri/bin/FastReadBackend"

cleanup() {
  rm -rf -- "$staging_dir"
}
trap cleanup EXIT

echo "Cleaning generated build directories..."
rm -rf -- backend/dist backend/build fastread-frontend/src-tauri/bin "$staging_dir"
mkdir -p "$staging_dir" fastread-frontend/src-tauri/bin

target_triple="$(rustc -Vv | awk '/^host:/ { print $2 }')"
test -n "$target_triple"
echo "Detected target triple: $target_triple"

echo "Building the isolated backend bundle..."
pyinstaller \
  -y \
  --name FastReadBackend \
  --paths backend \
  --distpath fastread-frontend/src-tauri/bin \
  --workpath backend/build \
  --specpath "$staging_dir" \
  --hidden-import uvicorn \
  --hidden-import fastapi \
  --hidden-import starlette \
  --add-data "backend/app/db/builtin_providers.json:." \
  backend/main.py

mv \
  "$bundle_dir/FastReadBackend" \
  "$bundle_dir/FastReadBackend-$target_triple"

echo "Scanning staged and generated files for private-key or high-confidence token material..."
secret_pattern='-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----|(sk|rk)-[A-Za-z0-9_-]{32,}|gh[pousr]_[A-Za-z0-9]{30,}|xox[baprs]-[A-Za-z0-9-]{20,}'
scan_roots=()
for root in "$staging_dir" backend/build backend/dist fastread-frontend/src-tauri/bin; do
  if [[ -d "$root" ]]; then
    scan_roots+=("$root")
  fi
done

bad_files=()
while IFS= read -r -d '' file; do
  if LC_ALL=C grep -IEql -- "$secret_pattern" "$file" 2>/dev/null; then
    bad_files+=("$(basename "$file")")
  fi
done < <(find "${scan_roots[@]}" -type f -print0)

if (( ${#bad_files[@]} > 0 )); then
  printf 'Potential secret material in artifact file(s):' >&2
  printf ' %s' "${bad_files[@]}" >&2
  printf '\n' >&2
  exit 1
fi

if find "$bundle_dir" -type f -name '.env' -print -quit | grep -q .; then
  echo "Packaged .env files are forbidden" >&2
  exit 1
fi
find "$bundle_dir" -type f -name 'builtin_providers.json' -print -quit | grep -q .

echo "PyInstaller bundle completed: $bundle_dir"

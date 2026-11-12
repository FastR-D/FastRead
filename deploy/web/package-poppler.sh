#!/usr/bin/env bash
set -euo pipefail
# Build on the same Ubuntu release as the deployment host.
mkdir -p bin lib/licenses
copy_license() {
  local package="$1"
  if [ -f "/usr/share/doc/$package/copyright" ]; then
    cp -L "/usr/share/doc/$package/copyright" "lib/licenses/${package//:/_}.copyright"
  fi
  dpkg-query -W -f='${source:Package} ${source:Version}\n' "$package" >> lib/licenses/source-packages.txt
}
copy_license poppler-utils
for program in pdftotext pdfinfo; do
  executable=$(command -v "$program")
  cp -L "$executable" "bin/$program"
  while IFS= read -r library; do
    cp -L "$library" "lib/$(basename "$library")"
    package=$(dpkg-query -S "$library" "$(readlink -f "$library")" 2>/dev/null | head -1 | sed 's/: \/.*//' || true)
    if [ -n "$package" ]; then copy_license "$package"; fi
  done < <(ldd "$executable" | awk '/=> \// {print $3}')
done
sort -u -o lib/licenses/source-packages.txt lib/licenses/source-packages.txt
printf '%s\n' 'Source packages: https://launchpad.net/ubuntu/+source/<package>/<version>' > lib/licenses/SOURCES.txt
LD_LIBRARY_PATH="$PWD/lib" bin/pdftotext -v
LD_LIBRARY_PATH="$PWD/lib" bin/pdfinfo -v

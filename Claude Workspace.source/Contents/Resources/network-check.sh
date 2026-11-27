base=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
if [[ -d "$base/region" ]]; then REGION_DIR="$base/region"; else REGION_DIR="$base/../../../region"; fi
. "$REGION_DIR/check.sh"

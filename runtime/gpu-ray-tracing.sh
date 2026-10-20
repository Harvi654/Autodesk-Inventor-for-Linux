# shellcheck shell=bash
# Source from a launcher after selecting its Wine prefix and graphics stack.
# Only D3D12 is replaced; per-application D3D11 overrides remain effective.
export WINEDLLOVERRIDES="d3d12,d3d12core=n${WINEDLLOVERRIDES:+;$WINEDLLOVERRIDES}"
export WINE_OPENGL_REQUIRE_ALPHA=1
inventor_gpu_cache="${XDG_CACHE_HOME:-$HOME/.cache}/autodesk-inventor-2026/vkd3d"
inventor_gpu_logs="${XDG_STATE_HOME:-$HOME/.local/state}/autodesk-inventor-2026"
mkdir -p "$inventor_gpu_cache" "$inventor_gpu_logs"
export VKD3D_SHADER_CACHE_PATH="$inventor_gpu_cache"
export VKD3D_LOG_FILE="$inventor_gpu_logs/vkd3d.log"
export VKD3D_DEBUG="${VKD3D_DEBUG:-info}"

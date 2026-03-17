#!/usr/bin/env bash
# ============================================================================
# Teukhos — Install Optional CLI Tools (Linux/macOS)
# ============================================================================
#
# PURPOSE:
#   Installs the CLI tools that Teukhos example servers wrap as MCP endpoints.
#   Each tool group is optional — you only need the ones for the servers you
#   plan to use. Run this before start-http-servers.sh to eliminate warnings.
#
# USAGE:
#   bash scripts/install-tools.sh              # Install all available tools
#   bash scripts/install-tools.sh --check      # Just check what's installed
#   bash scripts/install-tools.sh --group gpu   # Install only gpu tools
#
# GROUPS: git, media, gpu, docker, image, network, database, archive, kubernetes
#
# SEE ALSO:
#   scripts/install-tools.ps1       — Windows PowerShell equivalent
#   scripts/start-http-servers.sh   — Start the example HTTP servers
# ============================================================================

set -euo pipefail

# ── Tool groups ──────────────────────────────────────────────────────────────
# Each group maps to an example YAML config in examples/
declare -A GROUP_TOOLS=(
  [git]="git"
  [media]="ffmpeg ffprobe"
  [gpu]="nvidia-smi nvcc"
  [docker]="docker"
  [image]="magick"
  [network]="curl dig traceroute whois"
  [database]="sqlite3 psql"
  [archive]="tar zip unzip sha256sum"
  [kubernetes]="kubectl"
)

# APT package names for each tool (Ubuntu/Debian)
declare -A APT_PACKAGES=(
  [git]="git"
  [ffmpeg]="ffmpeg"
  [ffprobe]="ffmpeg"
  [nvidia-smi]="nvidia-utils-535"
  [nvcc]="nvidia-cuda-toolkit"
  [docker]="docker.io"
  [magick]="imagemagick"
  [curl]="curl"
  [dig]="dnsutils"
  [traceroute]="traceroute"
  [whois]="whois"
  [sqlite3]="sqlite3"
  [psql]="postgresql-client"
  [tar]="tar"
  [zip]="zip"
  [unzip]="unzip"
  [sha256sum]="coreutils"
  [kubectl]="kubectl"
)

# Brew package names for each tool (macOS)
declare -A BREW_PACKAGES=(
  [git]="git"
  [ffmpeg]="ffmpeg"
  [ffprobe]="ffmpeg"
  [magick]="imagemagick"
  [curl]="curl"
  [dig]="bind"
  [traceroute]="traceroute"
  [whois]="whois"
  [sqlite3]="sqlite"
  [psql]="postgresql"
  [tar]="gnu-tar"
  [zip]="zip"
  [unzip]="unzip"
  [sha256sum]="coreutils"
  [kubectl]="kubectl"
)

# ── Colors ───────────────────────────────────────────────────────────────────
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
DIM="\033[2m"
RESET="\033[0m"

# ── Detect platform ─────────────────────────────────────────────────────────
detect_platform() {
  if [[ "$(uname -s)" == "Darwin" ]]; then
    echo "macos"
  elif command -v apt-get &>/dev/null; then
    echo "apt"
  elif command -v dnf &>/dev/null; then
    echo "dnf"
  elif command -v pacman &>/dev/null; then
    echo "pacman"
  else
    echo "unknown"
  fi
}

# ── Check a single tool ─────────────────────────────────────────────────────
check_tool() {
  local tool="$1"
  if command -v "$tool" &>/dev/null; then
    local path
    path=$(command -v "$tool")
    printf "  ${GREEN}OK${RESET}     %-14s %s\n" "$tool" "$path"
    return 0
  else
    printf "  ${RED}MISSING${RESET}  %-14s\n" "$tool"
    return 1
  fi
}

# ── Check all tools ─────────────────────────────────────────────────────────
check_all() {
  echo ""
  echo "Teukhos Example Tools — Status"
  echo "=============================="
  echo ""

  local total=0
  local found=0

  for group in git media gpu docker image network database archive kubernetes; do
    echo -e "${DIM}── $group-tools ──${RESET}"
    for tool in ${GROUP_TOOLS[$group]}; do
      total=$((total + 1))
      if check_tool "$tool"; then
        found=$((found + 1))
      fi
    done
    echo ""
  done

  echo "Found $found / $total tools."
  if [[ $found -lt $total ]]; then
    echo -e "Run ${DIM}bash scripts/install-tools.sh${RESET} to install missing tools."
  else
    echo -e "${GREEN}All tools installed!${RESET}"
  fi
}

# ── Install tools for a group ────────────────────────────────────────────────
install_group() {
  local group="$1"
  local platform="$2"
  local to_install=()

  if [[ -z "${GROUP_TOOLS[$group]+x}" ]]; then
    echo -e "${RED}Unknown group: $group${RESET}"
    echo "Available groups: ${!GROUP_TOOLS[*]}"
    return 1
  fi

  echo -e "${DIM}── $group-tools ──${RESET}"

  for tool in ${GROUP_TOOLS[$group]}; do
    if command -v "$tool" &>/dev/null; then
      printf "  ${GREEN}OK${RESET}     %-14s (already installed)\n" "$tool"
    else
      case "$platform" in
        apt)    to_install+=("${APT_PACKAGES[$tool]:-}");;
        macos)  to_install+=("${BREW_PACKAGES[$tool]:-}");;
        *)      to_install+=("$tool");;
      esac
      printf "  ${YELLOW}QUEUE${RESET}  %-14s\n" "$tool"
    fi
  done

  # Deduplicate
  local unique_packages
  unique_packages=$(printf '%s\n' "${to_install[@]}" | grep -v '^$' | sort -u | tr '\n' ' ')

  if [[ -z "$unique_packages" || "$unique_packages" == " " ]]; then
    echo "  Nothing to install."
    return 0
  fi

  echo ""
  echo "  Installing: $unique_packages"

  case "$platform" in
    apt)
      sudo apt-get install -y $unique_packages
      ;;
    macos)
      brew install $unique_packages
      ;;
    dnf)
      sudo dnf install -y $unique_packages
      ;;
    pacman)
      sudo pacman -S --noconfirm $unique_packages
      ;;
    *)
      echo -e "  ${RED}Cannot auto-install on this platform.${RESET}"
      echo "  Please install manually: $unique_packages"
      return 1
      ;;
  esac
  echo ""
}

# ── Main ─────────────────────────────────────────────────────────────────────
MODE="install"
TARGET_GROUP=""

for arg in "$@"; do
  case "$arg" in
    --check)  MODE="check";;
    --group)  MODE="group";;
    *)
      if [[ "$MODE" == "group" ]]; then
        TARGET_GROUP="$arg"
      fi
      ;;
  esac
done

if [[ "$MODE" == "check" ]]; then
  check_all
  exit 0
fi

PLATFORM=$(detect_platform)
echo ""
echo "Teukhos Example Tools — Installer"
echo "=================================="
echo -e "Platform: ${DIM}$PLATFORM${RESET}"
echo ""

if [[ "$MODE" == "group" && -n "$TARGET_GROUP" ]]; then
  install_group "$TARGET_GROUP" "$PLATFORM"
else
  # Ask about GPU/CUDA before running
  INSTALL_GPU=false
  read -rp "Do you have an NVIDIA GPU with CUDA? (y/n) " gpu_answer
  if [[ "$gpu_answer" =~ ^[yY] ]]; then
    INSTALL_GPU=true
  else
    echo -e "  ${DIM}Skipping GPU/CUDA tools.${RESET}"
  fi
  echo ""

  # Install all groups (already-installed tools are detected and skipped)
  for group in git media gpu docker image network database archive kubernetes; do
    if [[ "$group" == "gpu" && "$INSTALL_GPU" == false ]]; then continue; fi
    install_group "$group" "$PLATFORM"
    echo ""
  done
fi

echo ""
echo "Done. Run 'bash scripts/install-tools.sh --check' to verify."

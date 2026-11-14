#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL="https://github.com/xinghunbuxiu/evo-agent"
RUNNER_DIR="${RUNNER_DIR:-$HOME/actions-runner}"
RUNNER_NAME="${RUNNER_NAME:-evo-agent-vps-$(hostname -s)}"
RUNNER_LABELS="self-hosted,linux,x64,evo-agent"

if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
  echo "This installer targets x86_64 Linux. For ARM64 VPS, use GitHub's ARM64 runner package and update workflow labels." >&2
  exit 1
fi
if [[ $EUID -eq 0 ]]; then
  echo "Do not run the GitHub Actions runner as root. Run this script as a dedicated non-root account with sudo access." >&2
  exit 1
fi
if ! command -v sudo >/dev/null || ! command -v curl >/dev/null || ! command -v jq >/dev/null || ! command -v tar >/dev/null; then
  echo "Missing prerequisites. On Debian/Ubuntu, install them with: sudo apt-get update && sudo apt-get install -y curl jq tar gzip ca-certificates" >&2
  exit 1
fi

mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"

if [[ ! -x ./config.sh ]]; then
  echo "Fetching latest official GitHub Actions runner release metadata..."
  release_json="$(curl --fail --silent --show-error --location https://api.github.com/repos/actions/runner/releases/latest)"
  tag="$(printf '%s' "$release_json" | jq -r '.tag_name')"
  asset_url="$(printf '%s' "$release_json" | jq -r '.assets[] | select(.name | test("^actions-runner-linux-x64-[0-9.]+\\.tar\\.gz$")) | .browser_download_url' | head -n 1)"
  if [[ -z "$tag" || "$tag" == "null" || -z "$asset_url" ]]; then
    echo "Could not identify the official Linux x64 runner asset from GitHub release metadata." >&2
    exit 1
  fi
  echo "Downloading runner release $tag"
  curl --fail --silent --show-error --location "$asset_url" -o runner.tar.gz
  tar xzf runner.tar.gz
  rm -f runner.tar.gz
fi

if [[ ! -f .runner ]]; then
  echo "Create a repository runner token in GitHub: Settings > Actions > Runners > New self-hosted runner."
  read -r -s -p "Paste the temporary runner registration token: " RUNNER_TOKEN
  printf '\n'
  if [[ -z "$RUNNER_TOKEN" ]]; then
    echo "Registration token cannot be empty." >&2
    exit 1
  fi
  trap 'unset RUNNER_TOKEN' EXIT
  ./config.sh --url "$REPO_URL" --token "$RUNNER_TOKEN" --name "$RUNNER_NAME" --labels "$RUNNER_LABELS" --work "_work" --unattended
  unset RUNNER_TOKEN
  trap - EXIT
else
  echo "Runner is already configured in $RUNNER_DIR; leaving its registration unchanged."
fi

if [[ ! -f .service ]]; then
  sudo ./svc.sh install "$USER"
fi
sudo ./svc.sh start
echo
echo "Runner service started. Verify it appears as Online in GitHub repository Settings > Actions > Runners."
echo "Runner directory: $RUNNER_DIR"
echo "Labels: $RUNNER_LABELS"

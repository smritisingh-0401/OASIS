#!/usr/bin/env bash
# Start the shared test version automatically on an Ubuntu host (docs/demo_host.md).
#
#   bash scripts/host_autostart.sh install     once: the model, OASIS and the link start at
#                                              every boot and restart if they stop
#   bash scripts/host_autostart.sh link        the current link to share (new after a restart)
#   bash scripts/host_autostart.sh status      are the three running?
#   bash scripts/host_autostart.sh restart     restart all three (gives a new link)
#   bash scripts/host_autostart.sh stop        stop now; they start again at the next boot
#   bash scripts/host_autostart.sh uninstall   stop them and remove the services
#
# Run it as the user who set up OASIS, not as root; it asks for the sudo password itself.
set -euo pipefail

SERVICES=(oasis-model oasis-app oasis-link)
OASIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_ARGS="-hf unsloth/Qwen3.5-4B-GGUF:Q4_K_M --no-mmproj --jinja -c 4096 -np 1 -ngl 0 --host 127.0.0.1 --port 8080"
LINK_PATTERN='https://[a-z0-9-]+\.trycloudflare\.com'

die() { echo "Error: $*" >&2; exit 1; }

find_bin() {  # the first of: on PATH, then the given paths
  local name=$1 path
  shift
  if path=$(command -v "$name"); then echo "$path"; return; fi
  for path in "$@"; do
    if [[ -x $path ]]; then echo "$path"; return; fi
  done
  die "cannot find $name. Install it first (docs/demo_host.md, step 1)."
}

write_unit() {  # name, description, after, workdir, command
  sudo tee "/etc/systemd/system/$1.service" > /dev/null <<EOF
[Unit]
Description=$2
Wants=network-online.target
After=network-online.target $3

[Service]
User=$USER
WorkingDirectory=$4
Environment=HOME=$HOME
Environment=PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=$5
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
}

current_link() {
  sudo journalctl -u oasis-link -o cat --no-pager 2>/dev/null | grep -oE "$LINK_PATTERN" | tail -n 1
}

install() {
  local llama uv cloudflared
  llama=$(find_bin llama-server "$HOME/llama.cpp/build/bin/llama-server")
  uv=$(find_bin uv "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv")
  cloudflared=$(find_bin cloudflared /usr/local/bin/cloudflared /usr/bin/cloudflared)

  if [[ ! -f $OASIS_DIR/.env ]]; then
    printf 'OASIS_DEMO=1\nOASIS_LLM_BACKEND=llama_server\nOASIS_STORAGE_BACKEND=memory\n' \
      > "$OASIS_DIR/.env"
    echo "Created $OASIS_DIR/.env (demo mode, real model, memory only)."
  elif ! grep -q '^OASIS_DEMO=1' "$OASIS_DIR/.env"; then
    echo "Warning: $OASIS_DIR/.env has no OASIS_DEMO=1, so the banner and test-version notice are off."
  fi

  echo "Writing the three services (sudo may ask for your password)..."
  write_unit oasis-model "OASIS language model (llama-server)" "" "$HOME" "$llama $MODEL_ARGS"
  write_unit oasis-app "OASIS" "oasis-model.service" "$OASIS_DIR" \
    "$uv run uvicorn oasis.api.app:create_app --factory --host 127.0.0.1 --port 8000"
  write_unit oasis-link "OASIS share link (Cloudflare quick tunnel)" "oasis-app.service" "$HOME" \
    "$cloudflared tunnel --url http://127.0.0.1:8000"
  sudo systemctl daemon-reload
  sudo systemctl enable --now "${SERVICES[@]}"

  echo "Started. Waiting for the link (up to a minute)..."
  local link="" _
  for _ in $(seq 30); do
    link=$(current_link) && [[ -n $link ]] && break
    sleep 2
  done
  if [[ -n $link ]]; then
    echo "Share this link: $link"
  else
    echo "No link yet. Try 'bash scripts/host_autostart.sh link' in a minute."
  fi
  echo "The model takes about a minute to load; replies before that get a short fixed reply."
}

case "${1:-}" in
  install)
    [[ $EUID -ne 0 ]] || die "run this as your own user, not with sudo or as root."
    install
    ;;
  link)
    link=$(current_link) || true
    [[ -n ${link:-} ]] || die "no link yet. Is it running? Try: bash scripts/host_autostart.sh status"
    echo "$link"
    ;;
  status)
    for s in "${SERVICES[@]}"; do printf '%-12s %s\n' "$s" "$(systemctl is-active "$s" || true)"; done
    ;;
  restart)
    sudo systemctl restart "${SERVICES[@]}"
    echo "Restarted. The link changes: run 'bash scripts/host_autostart.sh link' in a few seconds."
    ;;
  stop)
    sudo systemctl stop "${SERVICES[@]}"
    echo "Stopped. They start again at the next boot ('uninstall' to stop that)."
    ;;
  uninstall)
    sudo systemctl disable --now "${SERVICES[@]}" 2>/dev/null || true
    for s in "${SERVICES[@]}"; do sudo rm -f "/etc/systemd/system/$s.service"; done
    sudo systemctl daemon-reload
    echo "Removed. Nothing starts at boot any more."
    ;;
  *)
    sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac

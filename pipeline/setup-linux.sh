#!/usr/bin/env bash
# One-time setup for this project's Ubuntu Jenkins host.
# Run: sudo bash pipeline/setup-linux.sh
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

if [[ $EUID -ne 0 ]]; then
    echo 'Run this script with sudo: sudo bash pipeline/setup-linux.sh' >&2
    exit 1
fi
getent passwd jenkins >/dev/null || { echo 'Install Jenkins first.' >&2; exit 1; }
command -v docker >/dev/null || { echo 'Install Docker Engine and Docker Compose first.' >&2; exit 1; }
command -v ollama >/dev/null || { echo 'Install Ollama first.' >&2; exit 1; }

apt-get update
apt-get install -y python3 python3-venv python3-pip git curl ca-certificates xz-utils socat
python3 -c 'import sys; assert sys.version_info >= (3, 12), "Ubuntu 24.04 / Python 3.12+ is required"'

# Install a system-wide Node runtime. Jenkins cannot use a private nvm install.
if ! command -v node >/dev/null || ! node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 22 ? 0 : 1)'; then
    case "$(dpkg --print-architecture)" in
        amd64) node_arch=x64 ;;
        arm64) node_arch=arm64 ;;
        *) echo 'Unsupported Node.js architecture.' >&2; exit 1 ;;
    esac
    task_tmp=$(mktemp -d)
    trap 'rm -rf "$task_tmp"' EXIT
    node_url=https://nodejs.org/dist/latest-v24.x
    curl -fsSL "$node_url/SHASUMS256.txt" -o "$task_tmp/SHASUMS256.txt"
    archive=$(awk -v suffix="-linux-${node_arch}.tar.xz" 'index($2, suffix) && substr($2, length($2)-length(suffix)+1) == suffix {print $2}' "$task_tmp/SHASUMS256.txt")
    [[ -n "$archive" && "$archive" != *$'\n'* && "$archive" != */* ]]
    curl -fsSL "$node_url/$archive" -o "$task_tmp/$archive"
    (cd "$task_tmp"; awk -v name="$archive" '$2 == name' SHASUMS256.txt | sha256sum -c -)
    install -d /opt/acme-node /usr/local/bin
    tar -xJf "$task_tmp/$archive" -C /opt/acme-node --strip-components=1
    for tool in node npm npx; do
        ln -sfn "/opt/acme-node/bin/$tool" "/usr/local/bin/$tool"
    done
fi
node --version
npm --version
command -v google-chrome >/dev/null || { echo 'Install Google Chrome before building.' >&2; exit 1; }

systemctl enable --now docker ollama
docker compose version
usermod -aG docker jenkins

# Keep Ollama on localhost and forward only Docker's bridge address to it.
# This avoids exposing its API on the machine's LAN interfaces.
gateway=$(docker network inspect bridge --format '{{(index .IPAM.Config 0).Gateway}}')
curl --noproxy '*' -fsS http://127.0.0.1:11434/api/tags >/dev/null
if ! curl --noproxy '*' -fsS --connect-timeout 3 "http://${gateway}:11434/api/tags" >/dev/null 2>&1; then
    cat > /etc/systemd/system/acme-ollama-bridge.service <<EOF
[Unit]
Description=Forward Docker bridge connections to local Ollama
Requires=docker.service ollama.service
After=docker.service ollama.service
PartOf=docker.service

[Service]
DynamicUser=yes
ExecStart=/usr/bin/socat TCP4-LISTEN:11434,bind=${gateway},reuseaddr,fork TCP4:127.0.0.1:11434
Restart=on-failure
RestartSec=3
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes

[Install]
WantedBy=multi-user.target docker.service
EOF
    systemctl daemon-reload
    systemctl enable --now acme-ollama-bridge.service
fi
curl --noproxy '*' -fsS --retry 10 --retry-connrefused --retry-delay 1 "http://${gateway}:11434/api/tags" |
    python3 -c 'import json, sys; assert any(m["name"] == "qwen2.5:3b" for m in json.load(sys.stdin)["models"]), "Run ollama pull qwen2.5:3b, then rerun setup"'

# Restart so the service receives its docker group and system-wide PATH.
install -d /etc/systemd/system/jenkins.service.d
cat > /etc/systemd/system/jenkins.service.d/acme-path.conf <<'EOF'
[Service]
Environment="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
EOF
systemctl daemon-reload
systemctl restart jenkins

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# Feed the script on stdin so Jenkins need not access the user's checkout path.
runuser -u jenkins -- bash -s < "$script_dir/check-linux.sh"
echo 'System setup complete. Configure the pipeline job on this Linux Jenkins host; no custom node label is needed.'

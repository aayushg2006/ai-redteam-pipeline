#!/usr/bin/env bash
# Run as the build user, including from a noninteractive Jenkins shell.
set -euo pipefail

[[ $(uname -s) == Linux ]] || { echo 'This pipeline requires a Linux build node.' >&2; exit 1; }

for tool in python3 node npm git curl docker google-chrome; do
    command -v "$tool" >/dev/null || { echo "Missing tool: $tool" >&2; exit 1; }
done
python3 -c 'import sys, venv; assert sys.version_info >= (3, 12), "Python 3.12+ is required"'
node -e 'if (Number(process.versions.node.split(".")[0]) < 22) throw Error("Node.js 22+ is required")'
node --version
npm --version
google-chrome --version
docker info >/dev/null
docker compose version

# On native Linux, host-gateway reaches Docker's bridge address, not localhost.
gateway=$(docker network inspect bridge --format '{{(index .IPAM.Config 0).Gateway}}')
if ! tags=$(curl --noproxy '*' -fsS --connect-timeout 5 "http://${gateway}:11434/api/tags"); then
    echo 'Ollama is unreachable from Docker. Run: sudo bash pipeline/setup-linux.sh' >&2
    exit 1
fi
python3 -c 'import json, sys; models = json.load(sys.stdin)["models"]; assert any(m["name"] == "qwen2.5:3b" for m in models), "Run: ollama pull qwen2.5:3b"' <<< "$tags"
echo 'Linux prerequisites OK (including Docker access and Ollama on the Docker bridge).'

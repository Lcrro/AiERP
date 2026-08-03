#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNTIME="$HOME/.local/share/nexterp-openclaw-v0.5"
NODE_VERSION="22.22.3"
OPENCLAW_VERSION="2026.7.1-2"
DEEPSEEK_PROVIDER_VERSION="2026.7.1"
NODE_HOME="$RUNTIME/node-v$NODE_VERSION-linux-x64"
CLI_HOME="$RUNTIME/cli"
PROFILE_HOME="$HOME/.openclaw-nexterp"
WORKSPACE="$PROFILE_HOME/workspace"
ENV_DIR="$HOME/.config/nexterp"
ENV_FILE="$ENV_DIR/openclaw-nexterp.env"

mkdir -p "$RUNTIME" "$ENV_DIR" "$WORKSPACE/skills/nexterp-capability-manual"
mkdir -p "$HOME/.local/bin"
ln -sfn "$ROOT/scripts/openclaw/start_capability_api.sh" "$HOME/.local/bin/nexterp-capability-api-v05"
ln -sfn "$ROOT/scripts/openclaw/start_nexterp_gateway.sh" "$HOME/.local/bin/nexterp-openclaw-gateway-v05"
ln -sfn "$ROOT/scripts/openclaw/run_nexterp_agent.sh" "$HOME/.local/bin/nexterp-openclaw-agent-v05"

if [[ ! -x "$NODE_HOME/bin/node" ]]; then
  archive="$RUNTIME/node-v$NODE_VERSION-linux-x64.tar.xz"
  curl -fsSL "https://nodejs.org/dist/v$NODE_VERSION/node-v$NODE_VERSION-linux-x64.tar.xz" -o "$archive"
  tar -xJf "$archive" -C "$RUNTIME"
fi
export PATH="$NODE_HOME/bin:$PATH"

mkdir -p "$CLI_HOME"
if [[ ! -x "$CLI_HOME/node_modules/.bin/openclaw" ]]; then
  npm install --prefix "$CLI_HOME" --omit=dev "openclaw@$OPENCLAW_VERSION"
fi
OPENCLAW="$CLI_HOME/node_modules/.bin/openclaw"

if [[ ! -f "$ROOT/integrations/openclaw-nexterp/dist/index.js" ]]; then
  npm --prefix "$ROOT/integrations/openclaw-nexterp" run build
fi
mkdir -p "$RUNTIME/packages"
npm pack "$ROOT/integrations/openclaw-nexterp" --pack-destination "$RUNTIME/packages" >/dev/null
NEXTERP_PLUGIN="$(find "$RUNTIME/packages" -maxdepth 1 -name 'nexterp-openclaw-capability-plugin-*.tgz' | sort | tail -n 1)"
"$OPENCLAW" --profile nexterp plugins install --force "$NEXTERP_PLUGIN"
"$OPENCLAW" --profile nexterp plugins install --force "@openclaw/deepseek-provider@$DEEPSEEK_PROVIDER_VERSION"

cp "$ROOT/integrations/openclaw-nexterp/skill/SKILL.md" \
  "$WORKSPACE/skills/nexterp-capability-manual/SKILL.md"
cp "$ROOT/integrations/openclaw-nexterp/workspace/AGENTS.md" "$WORKSPACE/AGENTS.md"

if [[ ! -f "$ENV_FILE" ]]; then
  deepseek_key="$(sed -n 's/^DEEPSEEK_API_KEY=//p' "$ROOT/.env" | tail -n 1)"
  if [[ -z "$deepseek_key" || "$deepseek_key" == "replace-me" ]]; then
    echo "DEEPSEEK_API_KEY is missing from $ROOT/.env" >&2
    exit 1
  fi
  umask 077
  cat >"$ENV_FILE" <<EOF
DEEPSEEK_API_KEY=$deepseek_key
OPENCLAW_GATEWAY_TOKEN=$(openssl rand -hex 32)
NEXTERP_CAPABILITY_API_TOKEN=$(openssl rand -hex 32)
NEXTERP_CAPABILITY_API_URL=http://127.0.0.1:8790
NEXTERP_OPENCLAW_DEV_SUBJECT=nexterp-local-owner
NEXTERP_CAPABILITY_ERP_PROFILE=CIVIL
EOF
fi
chmod 600 "$ENV_FILE"
set -a
source "$ENV_FILE"
set +a

"$OPENCLAW" --profile nexterp config set gateway.mode local
"$OPENCLAW" --profile nexterp config set gateway.port 18829
"$OPENCLAW" --profile nexterp config set gateway.bind loopback
"$OPENCLAW" --profile nexterp config set gateway.auth.mode token
"$OPENCLAW" --profile nexterp config set agents.defaults.workspace "$WORKSPACE"
"$OPENCLAW" --profile nexterp config set agents.defaults.model.primary deepseek/deepseek-v4-flash
"$OPENCLAW" --profile nexterp config set models.providers.deepseek.apiKey \
  --ref-provider default --ref-source env --ref-id DEEPSEEK_API_KEY
"$OPENCLAW" --profile nexterp config set agents.defaults.skipBootstrap true
"$OPENCLAW" --profile nexterp config set tools.profile minimal
"$OPENCLAW" --profile nexterp config unset tools.allow >/dev/null 2>&1 || true
"$OPENCLAW" --profile nexterp config set tools.alsoAllow '["nexterp_load_work_context","nexterp_search_capabilities","nexterp_load_guide","nexterp_prepare_operation","nexterp_execute_prepared_operation"]' --strict-json
"$OPENCLAW" --profile nexterp config set plugins.allow '["deepseek","nexterp-capability"]' --strict-json
"$OPENCLAW" --profile nexterp config set plugins.entries.deepseek.enabled true
"$OPENCLAW" --profile nexterp config set plugins.entries.nexterp-capability.enabled true
"$OPENCLAW" --profile nexterp config set plugins.entries.nexterp-capability.config.baseUrl http://127.0.0.1:8790
"$OPENCLAW" --profile nexterp config set plugins.entries.nexterp-capability.config.requestTimeoutMs 30000

"$OPENCLAW" --profile nexterp config validate
"$OPENCLAW" --profile nexterp plugins doctor
printf 'Installed isolated Nexterp OpenClaw runtime: %s\n' "$OPENCLAW_VERSION"
printf 'Profile: %s | Gateway port: 18829 | Secrets: %s\n' "$PROFILE_HOME" "$ENV_FILE"

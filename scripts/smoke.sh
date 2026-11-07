#!/usr/bin/env bash
# End-to-end check: create keys, send a voice note, wait until it is routed.
#   dev : BASE=http://localhost:8000 ./scripts/smoke.sh
#   prod: BASE=https://sma3ni.example.ma AUDIO=sample.ogg ./scripts/smoke.sh
set -euo pipefail
BASE=${BASE:-http://localhost:8000}
COMPOSE=${COMPOSE:-docker compose -f docker-compose.yml -f docker-compose.dev.yml}

key() { $COMPOSE run --rm -T api python -m sma3ni.cli create-key "$@" | awk '/^key:/ {print $2}'; }
INTAKE=$(key --name "smoke-intake-$RANDOM" --scopes intake)
AGENT=$(key --name "smoke-agent-$RANDOM" --scopes agent)

if [ -z "${AUDIO:-}" ]; then
  AUDIO=$(mktemp --suffix=.wav)
  python3 - "$AUDIO" <<'EOF'
import math, struct, sys, wave
with wave.open(sys.argv[1], "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
    w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / 16000))) for i in range(32000)))
EOF
fi

echo "==> upload"
resp=$(curl -fsS -X POST "$BASE/v1/requests" -H "Authorization: Bearer $INTAKE" \
  -H "Idempotency-Key: smoke-$RANDOM" -F "audio=@$AUDIO" -F channel=whatsapp -F contact=+212600000000 -F region=Casablanca-Settat)
echo "$resp"
id=$(echo "$resp" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
code=$(echo "$resp" | python3 -c 'import json,sys; print(json.load(sys.stdin)["tracking_code"])')

echo "==> waiting for routing"
for _ in $(seq 1 120); do
  status=$(curl -fsS "$BASE/v1/requests/$id" -H "Authorization: Bearer $AGENT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')
  case "$status" in ROUTED|FAILED) break ;; esac
  sleep 2
done
curl -fsS "$BASE/v1/requests/$id" -H "Authorization: Bearer $AGENT" | python3 -m json.tool
echo "==> citizen view"
curl -fsS "$BASE/v1/track/$code" | python3 -m json.tool
[ "$status" = "ROUTED" ] && echo "SMOKE OK" || { echo "SMOKE FAILED ($status)"; exit 1; }

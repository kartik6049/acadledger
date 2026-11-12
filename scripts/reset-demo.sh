#!/usr/bin/env sh
# Start the demo from a clean slate: wipes the local database and uploaded files,
# brings the stack back up, seeds the demo accounts and writes two demo files.
#
#   ./scripts/reset-demo.sh
set -eu
cd "$(dirname "$0")/.."

printf 'This deletes ALL local AcadLedger data (database and uploaded files). Continue? [y/N] '
read -r answer
[ "$answer" = "y" ] || { echo "Cancelled."; exit 1; }

docker compose down --volumes
docker compose up -d

printf 'Waiting for the API'
until curl -sf http://localhost:8000/healthz >/dev/null 2>&1; do
    printf '.'
    sleep 2
done
echo

docker compose exec -T api python -m app.seed
docker compose exec -T api python scripts/generate_students.py \
    --rows 200 --programmes CSE,ECE,ME --errors 8 --out /app/data/demo-with-errors.csv
docker compose exec -T api python scripts/generate_students.py \
    --rows 200 --programmes CSE,ECE,ME --out /app/data/demo-clean.csv

echo
echo "Ready. Demo files are in api/data/. Start the web app with: cd web && pnpm dev"

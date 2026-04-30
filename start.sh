#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

if [ -f .venv/Scripts/activate ]; then
  source .venv/Scripts/activate
elif [ -f .venv/bin/activate ]; then
  source .venv/bin/activate
else
  echo "No .venv found. Run ./bootstrap.sh first."
  exit 1
fi

exec uvicorn app:app --port 5050 --reload --reload-exclude '*.pyc' --reload-exclude '__pycache__'

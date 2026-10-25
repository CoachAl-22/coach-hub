#!/bin/bash
set -e

pip install -r requirements.txt -q
npm ci --omit=dev --no-audit
python scripts/apply-dev-schema.py

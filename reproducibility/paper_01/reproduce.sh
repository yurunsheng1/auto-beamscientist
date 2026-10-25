#!/bin/sh
set -eu
cd "$(dirname "$0")/project"
python runs/pgcd/paper/source/validate_candidates.py
python runs/pgcd/paper/source/additional_controls.py
python runs/pgcd/paper/source/optimize_concentration.py

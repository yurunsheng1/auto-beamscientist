#!/bin/sh
set -eu
cd "$(dirname "$0")/project"
python runtime/paper_01/source/validate_candidates.py
python runtime/paper_01/source/additional_controls.py
python runtime/paper_01/source/optimize_concentration.py

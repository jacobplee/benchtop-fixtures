#!/bin/sh
# Rebuild everything: exports + checks, tests, renders, overview sheet.
#   ./make.sh              full run (Cycles renders take a few minutes on a laptop GPU)
#   ./make.sh --no-render  stop after the tests
# PYTHON and BLENDER override the interpreters.
set -e
cd "$(dirname "$0")"
PY=${PYTHON:-.venv/bin/python}
BLENDER=${BLENDER:-blender}
$PY -m benchtop_fixtures.build
$PY -m pytest -q
case " $* " in *" --no-render "*) exit 0 ;; esac
$BLENDER --background --python render/render_blender.py -- --samples=128 2>&1 | grep -E "wrote|Error|Traceback"
$PY render/overview.py

#!/usr/bin/env bash
# Create the project's Python 3.12 virtual environment (.venv312 by default), install the
# project with its dev tools, and run the test suite to confirm everything works.
# Any other environment (e.g. an existing .venv) is left untouched.
#
#   bash scripts/setup_env.sh                # creates .venv312
#   VENV_DIR=.myenv bash scripts/setup_env.sh
#
# Uses uv when available (it downloads Python 3.12 by itself); otherwise python3.12.
set -euo pipefail

PYTHON_VERSION="3.12"
VENV_DIR="${VENV_DIR:-.venv312}"
cd "$(dirname "$0")/.."

# 1. Refuse to reuse VENV_DIR if it exists but isn't a working Python 3.12 environment.
if [ -d "${VENV_DIR}" ] && ! "${VENV_DIR}/bin/python" -c \
    "import sys; sys.exit(sys.version_info[:2] != (3, 12))" 2>/dev/null; then
  echo "${VENV_DIR} exists but is not a working Python ${PYTHON_VERSION} environment." >&2
  echo "Remove it yourself or choose another name: VENV_DIR=.venv312b bash $0" >&2
  exit 1
fi

# 2. Create the environment and install the project (editable) with dev tools.
if command -v uv >/dev/null 2>&1; then
  [ -d "${VENV_DIR}" ] || uv venv --python "${PYTHON_VERSION}" "${VENV_DIR}"
  uv pip install --python "${VENV_DIR}/bin/python" -e ".[dev]"
else
  PYTHON_BIN="$(command -v "python${PYTHON_VERSION}" || true)"
  if [ -z "${PYTHON_BIN}" ]; then
    cat >&2 <<EOF
Python ${PYTHON_VERSION} was not found. Install one of these, then re-run this script:
  brew install uv            # recommended: uv fetches Python ${PYTHON_VERSION} automatically
  brew install python@3.12   # or the macOS installer from https://www.python.org/downloads/
EOF
    exit 1
  fi
  [ -d "${VENV_DIR}" ] || "${PYTHON_BIN}" -m venv "${VENV_DIR}"
  "${VENV_DIR}"/bin/python -m pip install --upgrade pip
  "${VENV_DIR}"/bin/python -m pip install -e ".[dev]"
fi

# 3. Verify: interpreter, CLI and tests (no network or LLM calls needed).
echo
"${VENV_DIR}"/bin/python --version
"${VENV_DIR}"/bin/seo-agent --version
echo "Running the test suite..."
if "${VENV_DIR}"/bin/python -m pytest -q; then
  echo "All tests passed."
else
  echo "Some tests failed; see the output above." >&2
fi

cat <<EOF

Environment ready.
  Activate:      source ${VENV_DIR}/bin/activate
  Verify LLM:    seo-agent --check-llm      (needs the API key for LLM_PROVIDER in .env)
  First run:     seo-agent --max-pages 20
EOF

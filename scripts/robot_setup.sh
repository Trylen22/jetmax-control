#!/usr/bin/env bash
set -euo pipefail

REPO="${HOME}/jetmax-control"

echo "JetMax repo setup"
echo "================="

if ! command -v git >/dev/null 2>&1; then
  echo "git is required but not installed."
  exit 1
fi

if [ ! -d "${REPO}/.git" ]; then
  echo "Cloning github.com/Trylen22/jetmax-control -> ${REPO}"
  git clone https://github.com/Trylen22/jetmax-control.git "${REPO}"
else
  echo "Updating ${REPO}"
  git -C "${REPO}" pull --ff-only
fi

mkdir -p "${REPO}/data"

if [ -f "${HOME}/saved_positions.json" ] && [ ! -f "${REPO}/data/saved_positions.json" ]; then
  cp "${HOME}/saved_positions.json" "${REPO}/data/saved_positions.json"
  echo "Migrated ~/saved_positions.json -> ${REPO}/data/saved_positions.json"
fi

if [ -f "${HOME}/jetmax_coord_log.csv" ] && [ ! -f "${REPO}/data/jetmax_coord_log.csv" ]; then
  cp "${HOME}/jetmax_coord_log.csv" "${REPO}/data/jetmax_coord_log.csv"
  echo "Migrated ~/jetmax_coord_log.csv -> ${REPO}/data/jetmax_coord_log.csv"
fi

chmod +x "${REPO}/run.sh" "${REPO}/scripts/robot_setup.sh"

echo
echo "Ready."
echo "  cd ${REPO}"
echo "  ./run.sh wasd"

#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO"

source_ros() {
  if [ -f "${HOME}/ros/devel/setup.bash" ]; then
    set +u
    # shellcheck disable=SC1091
    source "${HOME}/ros/devel/setup.bash"
    set -u
  fi
}

usage() {
  cat <<EOF
Usage: ./run.sh <command> [args...]

Commands:
  wasd          Keyboard arm controller
  hello         Basic ROS movement test
  plc-sim       PLC keyboard simulator
  plc-live      Live Allen Bradley integration
  plc-live-sim  PLC live in simulation mode
  plc-read      Read RobotCmd tag (no ROS)
  belt          Vision-guided belt pick
  belt-tcp      Belt vision with PLC TCP socket
  stream        MJPEG camera stream on :8080
  dashboard     Web control deck on :8888
  modb          Modbus toolkit (pass extra args)
  watch         Modbus register watcher

Examples:
  ./run.sh wasd
  ./run.sh modb watch --ip 192.168.1.10
EOF
}

cmd="${1:-}"
if [ -z "$cmd" ]; then
  usage
  exit 1
fi
shift || true

case "$cmd" in
  wasd) source_ros; exec python3 "$REPO/scripts/arm/wasd_control.py" ;;
  hello) source_ros; exec python3 "$REPO/scripts/arm/hello_jetmax.py" ;;
  plc-sim) source_ros; exec python3 "$REPO/scripts/plc/plc_sim.py" ;;
  plc-live) source_ros; exec python3 "$REPO/scripts/plc/plc_live.py" ;;
  plc-live-sim) source_ros; exec python3 "$REPO/scripts/plc/plc_live.py" --sim ;;
  plc-read) exec python3 "$REPO/scripts/plc/plc_read.py" ;;
  belt) source_ros; exec python3 "$REPO/scripts/vision/belt_vision.py" ;;
  belt-tcp) source_ros; exec python3 "$REPO/scripts/vision/belt_vision_socket_tcp.py" ;;
  stream) source_ros; exec python3 "$REPO/scripts/vision/stream.py" ;;
  dashboard) source_ros; exec python3 "$REPO/scripts/web/dashboard_server.py" ;;
  modb) exec python3 "$REPO/scripts/plc/modb.py" "$@" ;;
  watch) exec python3 "$REPO/scripts/plc/watch.py" "$@" ;;
  *)
    echo "Unknown command: $cmd"
    usage
    exit 1
    ;;
esac

#!/usr/bin/env bash
## bash only. Started with sh/dash (or any other shell), switch to bash first.
if [ -z "${BASH_VERSION:-}" ]; then exec bash "$0" "$@"; fi
# AI Generated -- new file, Claude (Anthropic), 2026-11. MIT, Yatharth Bhasin.
#
# Has the VideoCore message-loss race (raspberrypi/linux PR #7761) fired on this
# Pi since boot? Read-only, takes a second.
#
#   scripts/debug/vchiq_check.sh
#
# The kernel's message queue to the VideoCore can lose messages; vc-sm-cma then
# logs "vc_sm_cma_vchi_rx_ack: received response ..., throw away". Each loss
# pins a VideoCore slot until reboot; after 14 the VideoCore stops serving the
# camera ISP and the codec, which looks like a camera stall. Fixed only in
# 6.18 kernels (rpi-update 6.18.65 of 25 Nov 2026 has it); 6.12 lacks the fix.
# Also counts the other camera-stall fingerprints. Run it after long recordings,
# and on a scope whose recorder has hung, before rebooting.
# Logged to ~/diagnostics/vchiq_<host>_<stamp>.txt.
set -u

[ "$(uname)" = "Linux" ] || { echo "Linux only."; exit 1; }
[ "$(id -u)" -eq 0 ] || exec sudo bash "$0" "$@"

HOME_DIR=$(getent passwd "${SUDO_USER:-$USER}" | cut -d: -f6)
mkdir -p "$HOME_DIR/diagnostics"
OUT="$HOME_DIR/diagnostics/vchiq_$(hostname)_$(date +%Y_%m_%d__%Hh_%Mm).txt"

{
  echo "host:    $(hostname)"
  echo "kernel:  $(uname -r)"
  echo "booted:  $(uptime -s)   ($(uptime -p))"
  echo "checked: $(date '+%Y-%m-%d %H:%M:%S')"
  echo
  KLOG=$(journalctl -k -b --no-pager 2>/dev/null || dmesg -T)
  printf '%-36s %s\n' "fingerprint (since boot)" "count"
  for pat in "throw away" "Timeout waiting for buffers" "blocked for more than" \
             "Dequeue timer" "frontend has timed out" "vchiq" "I/O error"; do
    printf '%-36s %s\n' "$pat" "$(grep -c -i -- "$pat" <<<"$KLOG")"
  done
  echo
  N=$(grep -c -- "throw away" <<<"$KLOG")
  if [ "$N" -gt 0 ]; then
    echo "RACE FIRED: $N lost message(s) since boot (14 stops the camera). Lines:"
    grep -- "throw away" <<<"$KLOG" | tail -20
  else
    echo "No lost VideoCore messages since boot."
  fi
  echo
  echo "--- last vc_sm_cma / bcm2835-isp / vchiq lines ---"
  grep -i -E 'vc_sm_cma|bcm2835[-_]isp|vchiq' <<<"$KLOG" | tail -15
} | tee "$OUT"
chown "${SUDO_USER:-$USER}" "$OUT" 2>/dev/null
echo; echo "Saved: $OUT"

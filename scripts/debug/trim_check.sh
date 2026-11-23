#!/usr/bin/env bash
## bash only. Started with sh/dash (or any other shell), switch to bash first.
if [ -z "${BASH_VERSION:-}" ]; then exec bash "$0" "$@"; fi
# AI Generated -- new file, Claude (Anthropic), 2026-11. MIT, Yatharth Bhasin.
#
# Can the experiment SSD be TRIMmed through its USB adapter? Check, and
# optionally enable TRIM until the next reboot and run it once.
#
#   scripts/debug/trim_check.sh                 # check only (default mount below)
#   scripts/debug/trim_check.sh --trim          # check, enable, fstrim, read the kernel log
#   scripts/debug/trim_check.sh --trim /mnt/x   # another mount point
#
# The drives (NTech MX600, Samsung 870 QVO) report TRIM; whether it works
# depends on the adapter (ASMedia ASM1153, 174c:55aa) translating it. Some
# adapters claim support and then corrupt or brick the drive when TRIMmed, so
# --trim runs only when both checks pass, after a typed confirmation, and only
# on a scope whose SSD holds nothing that is not already on the NAS.
# Installs sg3-utils (and smartmontools) on first use if missing.
# Everything is logged to ~/diagnostics/trim_<host>_<stamp>.txt.
set -u

TRIM=0
[ "${1:-}" = "--trim" ] && { TRIM=1; shift; }
MOUNT="${1:-/home/trappyscope/ssd}"

[ "$(uname)" = "Linux" ] || { echo "Linux only."; exit 1; }
[ "$(id -u)" -eq 0 ] || exec sudo bash "$0" $([ $TRIM = 1 ] && echo --trim) "$MOUNT"

HOME_DIR=$(getent passwd "${SUDO_USER:-$USER}" | cut -d: -f6)
mkdir -p "$HOME_DIR/diagnostics"
LOG="$HOME_DIR/diagnostics/trim_$(hostname)_$(date +%Y_%m_%d__%Hhh_%Mmm_%Ss).txt"
exec > >(tee "$LOG") 2>&1

say()  { printf '%s\n' "$*"; }
fail() { say "STOP: $*"; say "Log: $LOG"; exit 1; }

## Which disk, and refuse anything but a mounted USB drive: if the SSD is not
## mounted, the folder is on the SD card, and that must never be touched here.
mountpoint -q "$MOUNT" || fail "$MOUNT is not a mount point (SSD not mounted?)."
PART=$(findmnt -no SOURCE --target "$MOUNT")
DISK=$(lsblk -no PKNAME "$PART" | head -1)
[ -n "$DISK" ] || DISK=$(basename "$PART")
if [[ "$DISK" == mmcblk* ]]; then fail "$MOUNT is on the SD card: $DISK"; fi
[ "$(lsblk -dno TRAN "/dev/$DISK")" = "usb" ] || fail "/dev/$DISK is not a USB drive."
## Tools: installed on first use (needs internet; the scopes reach it over wlan0).
need() {
    command -v "$1" >/dev/null && return
    say "Installing $2 (for $1)..."
    { apt-get install -y "$2" || { apt-get update -qq && apt-get install -y "$2"; }; } >/dev/null 2>&1
    command -v "$1" >/dev/null || fail "could not install $2 (no internet?). By hand: sudo apt install -y $2"
}
need sg_vpd sg3-utils
need smartctl smartmontools

SD=(/sys/block/$DISK/device/scsi_disk/*/provisioning_mode)
say "== $(hostname)  $(date '+%F %T')"
say "mount     $MOUNT -> $PART (disk /dev/$DISK)"
PROPS=$(udevadm info -q property -n "/dev/$DISK")
USBID="$(grep -m1 -E '^ID_(USB_)?VENDOR_ID=' <<< "$PROPS" | cut -d= -f2):$(grep -m1 -E '^ID_(USB_)?MODEL_ID=' <<< "$PROPS" | cut -d= -f2)"
say "adapter   ${USBID:-?}  $(lsblk -dno VENDOR "/dev/$DISK" | xargs)"
say "drive     $(lsblk -dno MODEL "/dev/$DISK" | xargs)"
say "kernel    provisioning_mode=$(cat "${SD[0]}")  discard_max_bytes=$(cat /sys/block/$DISK/queue/discard_max_bytes)"

UNMAP=$(sg_vpd -p bl "/dev/$DISK" 2>/dev/null | sed -n 's/.*Maximum unmap LBA count: *\([0-9]*\).*/\1/p' | head -1)
LBPV=$(sg_vpd -p lbpv "/dev/$DISK" 2>&1)
LBPU=$(sed -n 's/.*Unmap command supported (LBPU): *\([0-9]\).*/\1/p' <<< "$LBPV" | head -1)
[ -n "$LBPU" ] || LBPU="page not provided"
BLOCK=$(sg_readcap -l "/dev/$DISK" 2>/dev/null | sed -n 's/.*Logical block length=\([0-9]*\).*/\1/p' | head -1)
DRIVE_TRIM=$(smartctl -i "/dev/$DISK" 2>/dev/null | sed -n 's/^TRIM Command: *//p')
say "adapter   max unmap LBA count=${UNMAP:-?}  LBPU=${LBPU:-?}  block=${BLOCK:-?} B"
[ "$LBPU" = "page not provided" ] && say "          sg_vpd -p lbpv said: $(head -2 <<< "$LBPV" | paste -sd' ')"
say "drive     TRIM: ${DRIVE_TRIM:-not reported}"

ADAPTER_OK=0; [ "${UNMAP:-0}" -gt 0 ] 2>/dev/null && [ "${LBPU:-0}" = "1" ] && ADAPTER_OK=1
DRIVE_OK=0;   if [[ "${DRIVE_TRIM:-}" == Available* ]]; then DRIVE_OK=1; fi
say "verdict   adapter $([ $ADAPTER_OK = 1 ] && echo supports || echo 'does NOT report') UNMAP; drive $([ $DRIVE_OK = 1 ] && echo supports || echo 'does NOT report') TRIM"

[ $TRIM = 1 ] || { say "Check only. Add --trim to enable and run it."; say "Log: $LOG"; exit 0; }
[ $ADAPTER_OK = 1 ] && [ $DRIVE_OK = 1 ] || fail "not both supported; TRIM not attempted."

say ""
say "This enables TRIM on /dev/$DISK until the next reboot and trims all free space on $MOUNT."
say "If the adapter mistranslates it, the drive can be corrupted. Is everything on it on the NAS?"
read -r -p "Type TRIM to continue: " ANSWER < /dev/tty
[ "$ANSWER" = "TRIM" ] || fail "not confirmed."

N0=$(dmesg | wc -l)
echo unmap > "${SD[0]}" || fail "could not set provisioning_mode."
HW=$(cat /sys/block/$DISK/queue/discard_max_hw_bytes)
WANT=$(( UNMAP * ${BLOCK:-512} ))
[ "$HW" -gt 0 ] && [ "$WANT" -gt "$HW" ] && WANT=$HW
echo "$WANT" > /sys/block/$DISK/queue/discard_max_bytes || say "note: discard_max_bytes not set"
say "enabled   provisioning_mode=$(cat "${SD[0]}")  discard_max_bytes=$(cat /sys/block/$DISK/queue/discard_max_bytes)"

T0=$(date +%s)
fstrim -v "$MOUNT"; RC=$?
say "fstrim    exit $RC after $(( $(date +%s) - T0 )) s"
## Resets count only when they name the disk: the KVM's USB hub resets too.
NEW=$(dmesg | tail -n +"$((N0 + 1))")
BAD=$( { grep -iE "illegal request|critical target error|invalid field|I/O error|DISCARD|offline" <<< "$NEW"
         grep -iE "reset" <<< "$NEW" | grep -iE "uas|scsi|sd |$DISK"; } | sort -u)
if [ -n "$BAD" ] || [ $RC -ne 0 ]; then
    echo full > "${SD[0]}" 2>/dev/null
    say "FAILED. Kernel said:"; say "$BAD"
    say "TRIM switched back off. Reboot, and do not use TRIM on this adapter."
    say "Log: $LOG"; exit 1
fi
say "OK: no errors in the kernel log. TRIM stays on until the next reboot."
say "Log: $LOG"

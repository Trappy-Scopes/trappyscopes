#!/usr/bin/env bash
## bash only. Started with sh/dash (or any other shell), switch to bash first.
if [ -z "${BASH_VERSION:-}" ]; then exec bash "$0" "$@"; fi
# AI Generated -- new file, Claude (Anthropic), 2026-11. MIT, Yatharth Bhasin.
#
# Force TRIM through a USB adapter that does not report support, in the
# smallest possible dose, and check whether it reached the drive.
#
#   bash scripts/debug/trim_force_test.sh               # 64 MB test on the experiment SSD
#   bash scripts/debug/trim_force_test.sh --more 1G     # then, if clean, trim the first 1G too
#   bash scripts/debug/trim_force_test.sh /mnt/x        # another mount point
#
# 1. writes a 64 MB file of a marker text and finds its blocks on the disk
# 2. deletes it, switches TRIM on, trims exactly those 64 MB
# 3. reads the blocks back raw: marker gone = the TRIM reached the drive
# 4. checks the kernel log after every step; any adapter error stops it
# TRIM is switched back to its original setting at the end. trim_check.sh is
# the strict, supported path; this is the experiment. Run it only on a drive
# whose contents are all on the NAS: a mistranslated TRIM can corrupt a drive.
# Logged to ~/diagnostics/trim_force_<host>_<stamp>.txt.
set -u

MORE=""; MOUNT="/home/trappyscope/ssd"
while [ $# -gt 0 ]; do
    if [ "$1" = "--more" ]; then MORE="${2:-}"; shift 2; else MOUNT="$1"; shift; fi
done

[ "$(uname)" = "Linux" ] || { echo "Linux only."; exit 1; }
[ "$(id -u)" -eq 0 ] || exec sudo bash "$0" ${MORE:+--more "$MORE"} "$MOUNT"

HOME_DIR=$(getent passwd "${SUDO_USER:-$USER}" | cut -d: -f6)
mkdir -p "$HOME_DIR/diagnostics"
LOG="$HOME_DIR/diagnostics/trim_force_$(hostname)_$(date +%Y_%m_%d__%Hhh_%Mmm_%Ss).txt"
exec > >(tee "$LOG") 2>&1

say()  { printf '%s\n' "$*"; }
end()  { [ -n "${PM:-}" ] && [ -n "${MODE0:-}" ] && echo "$MODE0" > "$PM" 2>/dev/null
         say "TRIM setting restored: provisioning_mode=$(cat "$PM" 2>/dev/null)"; say "Log: $LOG"; exit "$1"; }
fail() { say "STOP: $*"; end 1; }
## New kernel lines since N0 that mean the adapter rejected or mangled a command.
## Resets count only when they name the disk: the KVM's USB hub resets too.
errors() {
    local new; new=$(dmesg | tail -n +"$((N0 + 1))")
    { grep -iE "illegal request|critical target error|invalid field|invalid command|I/O error|DISCARD|offline" <<< "$new"
      grep -iE "reset" <<< "$new" | grep -iE "uas|scsi|sd |$DISK"; } | sort -u
}

## Same guards as trim_check.sh: a mounted USB drive, never the SD card.
mountpoint -q "$MOUNT" || fail "$MOUNT is not a mount point (SSD not mounted?)."
PART=$(findmnt -no SOURCE --target "$MOUNT")
DISK=$(lsblk -no PKNAME "$PART" | head -1); [ -n "$DISK" ] || DISK=$(basename "$PART")
if [[ "$DISK" == mmcblk* ]]; then fail "$MOUNT is on the SD card: $DISK"; fi
[ "$(lsblk -dno TRAN "/dev/$DISK")" = "usb" ] || fail "/dev/$DISK is not a USB drive."
[ "$(findmnt -no FSTYPE --target "$MOUNT")" = "ext4" ] || fail "only ext4 is handled (block mapping)."
command -v filefrag >/dev/null || fail "filefrag missing (e2fsprogs)."

PM=$(ls /sys/block/$DISK/device/scsi_disk/*/provisioning_mode 2>/dev/null | head -1)
[ -f "$PM" ] || fail "no provisioning_mode for /dev/$DISK."
MODE0=""
BS=$(stat -f -c %S "$MOUNT")
say "== $(hostname)  $(date '+%F %T')"
say "mount     $MOUNT -> $PART (disk /dev/$DISK), fs block $BS B"
say "drive     $(lsblk -dno MODEL "/dev/$DISK" | xargs)"
say "before    provisioning_mode=$(cat "$PM")  discard_max_bytes=$(cat /sys/block/$DISK/queue/discard_max_bytes)"
say ""
say "This forces TRIM on /dev/$DISK, which its adapter may not support."
say "Everything on $MOUNT must already be on the NAS."
read -r -p "Type FORCE to continue: " ANSWER < /dev/tty
[ "$ANSWER" = "FORCE" ] || fail "not confirmed."
MODE0=$(cat "$PM")

## 1. A 64 MB marker file, on disk, and where it sits.
MARK="TRIMTEST-MARKER"                       # 15 chars + newline = 16 B, from yes(1)
FILE="$MOUNT/.trim_force_test_$$"
yes "$MARK" | head -c $((64 * 1024 * 1024)) > "$FILE"; sync
## Extent 0's physical start and length. A regex, not awk fields: filefrag pads
## to fixed widths, so a wide number runs into "..", e.g. "34816..51199:".
EXT=$(filefrag -v "$FILE" | sed -n 's/^ *0: *[0-9]*\.\. *[0-9]*: *\([0-9]*\)\.\. *[0-9]*: *\([0-9]*\):.*/\1 \2/p' | head -1)
START=${EXT%% *}; LEN=${EXT##* }
[ -n "$START" ] && [ -n "$LEN" ] || { rm -f "$FILE"; fail "could not read the file's block map."; }
[ "$LEN" -gt 256 ] && LEN=256                 # 1 MB at 4 KB blocks is plenty to read back
readback() { dd if="$PART" bs="$BS" skip="$START" count="$LEN" iflag=direct status=none | grep -ac "^$MARK$"; }
BEFORE=$(readback)
say "marker    $FILE: blocks $START+$LEN, $BEFORE marker lines read raw before deleting"
[ "$BEFORE" -gt 0 ] || { rm -f "$FILE"; fail "marker not found where filefrag says (mapping wrong); nothing trimmed."; }
rm -f "$FILE"; sync

## 2. TRIM on, and trim exactly that extent.
N0=$(dmesg | wc -l)
echo unmap > "$PM" || fail "could not set provisioning_mode."
say "forced    provisioning_mode=$(cat "$PM")  discard_max_hw_bytes=$(cat /sys/block/$DISK/queue/discard_max_hw_bytes)  discard_max_bytes=$(cat /sys/block/$DISK/queue/discard_max_bytes)"
[ "$(cat /sys/block/$DISK/queue/discard_max_bytes)" -gt 0 ] || fail "the kernel did not enable discard even when forced; nothing was sent to the drive."
fstrim -v --offset $((START * BS)) --length $((LEN * BS)) "$MOUNT"; RC=$?
BAD=$(errors)
say "fstrim    exit $RC on blocks $START+$LEN"
if [ -n "$BAD" ] || [ $RC -ne 0 ]; then
    say "FAILED: the adapter rejected it. Kernel said:"; say "${BAD:-(nothing, but fstrim failed)}"
    say "Reboot to be sure the drive is back to normal. TRIM is not usable on this adapter."
    end 1
fi

## 3. Did it reach the drive?
sleep 2
AFTER=$(readback)
say "readback  $AFTER marker lines after TRIM (was $BEFORE)"
if [ "$AFTER" -eq 0 ]; then
    say "RESULT    the TRIM reached the drive: the trimmed blocks no longer hold the data."
else
    say "RESULT    no kernel errors, but the data is still there. Either the TRIM did not reach the"
    say "          drive, or the drive keeps trimmed blocks readable until it erases them later."
fi

## 4. Optional larger range, only after a clean small one.
if [ -n "$MORE" ]; then
    N0=$(dmesg | wc -l)
    fstrim -v --length "$MORE" "$MOUNT"; RC=$?
    BAD=$(errors)
    if [ -n "$BAD" ] || [ $RC -ne 0 ]; then
        say "FAILED on --more $MORE. Kernel said:"; say "${BAD:-(nothing, but fstrim failed)}"
        say "Reboot to be sure the drive is back to normal."; end 1
    fi
    say "more      first $MORE trimmed cleanly (exit $RC, no kernel errors)"
fi
end 0

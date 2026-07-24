#!/usr/bin/env bash
# One-time host hardening/resilience checklist for infra/compose-host, per
# references/infra/home-infra.md's "five separate failure modes". This
# script checks and reports; it does NOT apply BIOS settings (nothing in
# software can — home-infra.md) and only touches systemd units with your
# confirmation. Run once when a host is first provisioned, and again after
# any OS reinstall.
set -uo pipefail

echo "== infra/compose-host host checklist (home-infra.md) =="

check() { printf '%-55s' "$1"; }

check "Docker installed + docker compose v2 plugin"
if docker compose version >/dev/null 2>&1; then echo "OK"; else echo "MISSING — install Docker Engine + compose-plugin"; fi

check "Sleep/suspend/hibernate masked"
if systemctl is-enabled sleep.target 2>/dev/null | grep -q masked; then
  echo "OK"
else
  echo "NOT MASKED — run: sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target"
fi

check "systemd watchdog configured (RuntimeWatchdogSec)"
if grep -q '^RuntimeWatchdogSec=' /etc/systemd/system.conf 2>/dev/null; then
  echo "OK"
else
  echo "NOT SET — add RuntimeWatchdogSec=20s, RebootWatchdogSec=10min to /etc/systemd/system.conf"
fi

check "kernel.panic sysctl (auto-reboot on panic)"
if sysctl kernel.panic 2>/dev/null | grep -qv 'panic = 0'; then echo "OK"; else echo "NOT SET — sysctl -w kernel.panic=10 (and persist in /etc/sysctl.d/)"; fi

check "tailscaled enabled at boot (if this host uses Tailscale)"
if systemctl is-enabled tailscaled >/dev/null 2>&1; then echo "OK"; else echo "N/A or not enabled — 'sudo systemctl enable tailscaled' if this host is on a tailnet"; fi

check "unattended-upgrades installed"
if dpkg -s unattended-upgrades >/dev/null 2>&1; then echo "OK"; else echo "MISSING — apt install unattended-upgrades (or the distro equivalent)"; fi

cat <<'EOF'

Cannot be checked/set from software (do these in BIOS/UEFI and the
Tailscale admin console by hand — home-infra.md):
  - "Restore on AC Power Loss" / "After Power Failure" -> Power On
  - Wake-on-LAN enabled in BIOS (if used as a power-off backstop)
  - Key expiry disabled on this node in the Tailscale admin console
    (an always-on host must never silently drop off the tailnet)
EOF

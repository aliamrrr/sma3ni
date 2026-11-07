#!/usr/bin/env bash
# EC2 user data (first boot, as root) for the AWS Deep Learning Base GPU AMI (Ubuntu 22.04).
# The AMI already ships the NVIDIA driver, Docker and nvidia-container-toolkit; this script
# makes sure Docker Compose v2 is present, wires the NVIDIA runtime and hardens the host.
# Log: /var/log/cloud-init-output.log
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
APP_USER=ubuntu

echo "==> automatic security updates"
apt-get update
apt-get install -y ca-certificates curl git unattended-upgrades
dpkg-reconfigure -f noninteractive unattended-upgrades

echo "==> docker engine + compose plugin"
if ! docker compose version >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    >/etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

echo "==> NVIDIA container runtime"
if command -v nvidia-ctk >/dev/null 2>&1; then
  nvidia-ctk runtime configure --runtime=docker
fi
systemctl enable --now docker
systemctl restart docker
usermod -aG docker "$APP_USER"

echo "==> sshd: no root login, no passwords"
cat >/etc/ssh/sshd_config.d/10-hardening.conf <<'CONF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
X11Forwarding no
MaxAuthTries 3
CONF
systemctl reload ssh || systemctl reload sshd || true

echo "==> GPU check"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv || echo "WARNING: nvidia-smi failed"

echo "bootstrap done"

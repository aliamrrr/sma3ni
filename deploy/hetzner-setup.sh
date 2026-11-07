#!/usr/bin/env bash
# One-time hardening of a fresh Hetzner Ubuntu 24.04 server. Run as root:
#   scp deploy/hetzner-setup.sh root@SERVER:/root/ && ssh root@SERVER bash /root/hetzner-setup.sh
# Prerequisite: your SSH public key was added when creating the server.
set -euo pipefail

DEPLOY_USER=${DEPLOY_USER:-deploy}
SWAP_GB=${SWAP_GB:-8}

echo "==> system updates + automatic security updates"
export DEBIAN_FRONTEND=noninteractive
apt-get update && apt-get -y upgrade
apt-get install -y ca-certificates curl git ufw fail2ban unattended-upgrades
dpkg-reconfigure -f noninteractive unattended-upgrades

echo "==> deploy user (key-only ssh, docker group)"
id "$DEPLOY_USER" >/dev/null 2>&1 || adduser --disabled-password --gecos "" "$DEPLOY_USER"
install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"
install -m 600 -o "$DEPLOY_USER" -g "$DEPLOY_USER" /root/.ssh/authorized_keys "/home/$DEPLOY_USER/.ssh/authorized_keys"

echo "==> sshd: no root login, no passwords"
cat >/etc/ssh/sshd_config.d/10-hardening.conf <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
X11Forwarding no
MaxAuthTries 3
EOF
systemctl reload ssh

echo "==> firewall (also create a Hetzner Cloud Firewall with the same rules: 22, 80, 443)"
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable
systemctl enable --now fail2ban

echo "==> docker engine (official repository)"
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  >/etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
cat >/etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "5" },
  "live-restore": true,
  "no-new-privileges": true,
  "userland-proxy": false
}
EOF
systemctl restart docker
usermod -aG docker "$DEPLOY_USER"

echo "==> ${SWAP_GB}G swap (safety net for ASR memory peaks)"
if ! swapon --show | grep -q /swapfile; then
  fallocate -l "${SWAP_GB}G" /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo "/swapfile none swap sw 0 0" >>/etc/fstab
  sysctl -w vm.swappiness=10 && echo "vm.swappiness=10" >/etc/sysctl.d/99-swappiness.conf
fi

echo "==> CPU check: avx512_bf16 means ASR_DTYPE=bfloat16 is fast; otherwise try float32"
grep -o -m1 'avx512_bf16' /proc/cpuinfo || echo "no avx512_bf16 on this CPU"

echo "done. Log in again as: ssh $DEPLOY_USER@<server>"

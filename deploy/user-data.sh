#!/bin/bash
# EC2 user data for Amazon Linux 2023 (t3.micro). Runs once on first boot: installs Docker and
# the compose plugin and adds swap. The app files arrive later through deploy/ship.sh.
set -euxo pipefail

dnf install -y docker
systemctl enable --now docker

COMPOSE_VERSION=v2.29.7
mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-$(uname -m)" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# 1 GB of RAM is tight while xhtml2pdf renders invoices
if [ ! -f /swapfile ]; then
  dd if=/dev/zero of=/swapfile bs=1M count=2048
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

mkdir -p /opt/pharmacore

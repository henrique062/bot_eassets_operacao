#!/bin/bash
# Setup completo VPS Hetzner — Phoenix Bot
# Roda como root uma única vez
set -e

echo "=== [1/7] Atualizando sistema ==="
export DEBIAN_FRONTEND=noninteractive
apt-get update -q && apt-get upgrade -yq

echo "=== [2/7] Instalando dependências ==="
apt-get install -yq \
    curl wget git ufw fail2ban htop \
    ca-certificates gnupg lsb-release

echo "=== [3/7] Instalando Docker ==="
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update -q
apt-get install -yq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

systemctl enable docker
systemctl start docker
docker --version
docker compose version

echo "=== [4/7] Instalando Portainer CE ==="
docker volume create portainer_data
docker run -d \
    --name portainer \
    --restart=always \
    -p 9443:9443 \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v portainer_data:/data \
    portainer/portainer-ce:latest

echo "=== [5/7] Configurando firewall (UFW) ==="
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw allow 3000/tcp  # Frontend Next.js
ufw allow 8000/tcp  # Python API
ufw allow 9443/tcp  # Portainer
ufw --force enable
ufw status

echo "=== [6/7] Configurando fail2ban ==="
systemctl enable fail2ban
systemctl start fail2ban

echo "=== [7/7] Criando diretório do projeto ==="
mkdir -p /opt/phoenix-bot
cd /opt/phoenix-bot

echo ""
echo "============================================"
echo "  SETUP CONCLUIDO!"
echo "============================================"
echo "  Docker:    $(docker --version)"
echo "  Portainer: https://$(curl -s ifconfig.me):9443"
echo "  Projeto:   /opt/phoenix-bot"
echo ""
echo "  PROXIMO PASSO: fazer upload do projeto e"
echo "  configurar o .env"
echo "============================================"

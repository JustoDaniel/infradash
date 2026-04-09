#!/bin/bash
# =============================================================
# InfraDash — Script de instalação
# Compatível com Ubuntu 24 LTS
# =============================================================

set -e
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC}  $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

INSTALL_DIR="/opt/infradash"
SERVICE_USER="infradash"
PORT=8765

info "=== InfraDash Install ==="
[[ $EUID -ne 0 ]] && error "Execute como root: sudo bash install.sh"

# --- Dependências do sistema ---
info "Instalando dependências do sistema..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv nginx libvirt-dev pkg-config gcc \
    python3-dev curl git virtinst qemu-kvm libvirt-daemon-system libvirt-clients

# --- Criar usuário de serviço ---
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd -r -s /bin/false -G libvirt "$SERVICE_USER"
    info "Usuário $SERVICE_USER criado"
fi

# --- Copiar arquivos do projeto ---
info "Instalando arquivos em $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
cp -r "$(dirname "$0")"/* "$INSTALL_DIR/"
chown -R "$SERVICE_USER":"$SERVICE_USER" "$INSTALL_DIR"

# --- Ambiente virtual Python ---
info "Criando virtualenv e instalando dependências Python..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install -q --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -q \
    flask gunicorn \
    boto3 \
    google-cloud-billing google-cloud-monitoring google-auth \
    oci \
    psutil \
    libvirt-python \
    python-dotenv \
    requests

# --- Arquivo de configuração (.env) ---
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    warn "Arquivo .env criado em $INSTALL_DIR/.env — edite com suas credenciais!"
fi

# --- Serviço systemd ---
info "Configurando serviço systemd..."
cat > /etc/systemd/system/infradash.service << EOF
[Unit]
Description=InfraDash — Cloud & Homelab Dashboard
After=network.target libvirtd.service

[Service]
Type=notify
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$INSTALL_DIR/venv/bin/gunicorn \
    --workers 2 \
    --bind 127.0.0.1:$PORT \
    --timeout 30 \
    --log-level info \
    --access-logfile $INSTALL_DIR/logs/access.log \
    --error-logfile $INSTALL_DIR/logs/error.log \
    backend.app:app
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

mkdir -p "$INSTALL_DIR/logs"
chown "$SERVICE_USER":"$SERVICE_USER" "$INSTALL_DIR/logs"

# --- Nginx ---
info "Configurando Nginx..."
cat > /etc/nginx/sites-available/infradash << EOF
server {
    listen 80;
    server_name localhost infradash.local;

    # Futuramente: server_name infra.justodaniel.com.br;

    location /api/ {
        proxy_pass http://127.0.0.1:$PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_read_timeout 30;
    }

    location / {
        root $INSTALL_DIR/frontend;
        index index.html;
        try_files \$uri \$uri/ /index.html;
    }
}
EOF

ln -sf /etc/nginx/sites-available/infradash /etc/nginx/sites-enabled/infradash
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# --- Ativar e iniciar serviço ---
systemctl daemon-reload
systemctl enable infradash
systemctl start infradash

info "=== Instalação concluída ==="
info "Dashboard disponível em: http://localhost"
info "API disponível em:       http://localhost/api/summary"
warn "Não esqueça de editar: $INSTALL_DIR/.env"

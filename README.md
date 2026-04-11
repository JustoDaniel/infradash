<div align="center">

```
██╗███╗   ██╗███████╗██████╗  █████╗ ██████╗  █████╗ ███████╗██╗  ██╗
██║████╗  ██║██╔════╝██╔══██╗██╔══██╗██╔══██╗██╔══██╗██╔════╝██║  ██║
██║██╔██╗ ██║█████╗  ██████╔╝███████║██║  ██║███████║███████╗███████║
██║██║╚██╗██║██╔══╝  ██╔══██╗██╔══██║██║  ██║██╔══██║╚════██║██╔══██║
██║██║ ╚████║██║     ██║  ██║██║  ██║██████╔╝██║  ██║███████║██║  ██║
╚═╝╚═╝  ╚═══╝╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝
```

**Homelab · Cloud Control Plane**

*Monitore seus custos em múltiplas nuvens e recursos locais em um único painel.*

[![Deploy InfraDash](https://github.com/JustoDaniel/infradash/actions/workflows/deploy.yml/badge.svg)](https://github.com/JustoDaniel/infradash/actions/workflows/deploy.yml)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask)
![Ubuntu](https://img.shields.io/badge/Ubuntu-24_LTS-E95420?logo=ubuntu&logoColor=white)
![Clouds](https://img.shields.io/badge/Clouds-AWS%20%7C%20GCP%20%7C%20OCI%20%7C%20Azure%20%7C%20DO-0069ff)
![License](https://img.shields.io/badge/license-MIT-green)

</div>

---

## 📌 O que é o InfraDash?

O **InfraDash** é um dashboard leve de monitoramento hospedado no seu próprio homelab. Ele centraliza em uma única tela:

- 💸 **Custo atual** de cada cloud (AWS, GCP, OCI, Azure, DigitalOcean) com breakdown por serviço
- 🔍 **Comparador de preços** — configure vCPU, RAM e horas e veja qual cloud está mais barata agora, com preços reais via APIs públicas e cache de 24h
- 🖥️ **Recursos do homelab** — CPU, RAM e disco em tempo real
- 🤖 **Máquinas virtuais KVM** — quais estão ligadas, suas specs e uptime

Tudo isso com uma esteira CI/CD completa: cada `git push` na branch `main` faz deploy automático no servidor via GitHub Actions + Tailscale + SSH.

---

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────────────┐
│                        FLUXO DE DEPLOY                          │
│                                                                 │
│   git push         GitHub Actions        Tailscale VPN          │
│  ──────────►  ──────────────────────►  ──────────────────►      │
│   main            ubuntu-latest             SSH :22             │
│                                               │                 │
│                                               ▼                 │
│                                     /opt/infradash (prod)       │
│                                     systemctl restart           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     ARQUITETURA DA APLICAÇÃO                    │
│                                                                 │
│   Navegador                                                     │
│      │  HTTP :80                                                │
│      ▼                                                          │
│   Nginx  (proxy reverso)                                        │
│      │  :8765                                                   │
│      ▼                                                          │
│   Gunicorn + Flask  (backend)                                   │
│      │                                                          │
│      ├──► AWS Cost Explorer API        ──► cache 1h             │
│      ├──► GCP Cloud Billing API        ──► cache 1h             │
│      ├──► OCI Usage & Cost API         ──► cache 1h             │
│      ├──► Azure Cost Management API    ──► cache 1h             │
│      ├──► DigitalOcean Billing API     ──► cache 1h             │
│      ├──► Pricing APIs (público)       ──► cache 24h            │
│      │     ├── AWS Price List API                               │
│      │     ├── GCP Billing Catalog API                          │
│      │     ├── Azure Retail Prices API                          │
│      │     ├── OCI Pricing API                                  │
│      │     └── DigitalOcean Droplets                            │
│      └──► psutil + libvirt (local)     ──► cache 30s            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📁 Estrutura do Projeto

```
infradash/
├── .github/
│   └── workflows/
│       └── deploy.yml          # Pipeline CI/CD
├── backend/
│   ├── app.py                  # Flask API + cache em memória
│   └── collectors/
│       ├── aws.py              # AWS Cost Explorer
│       ├── gcp.py              # GCP Cloud Billing
│       ├── oci.py              # OCI Usage & Cost Reports
│       ├── azure.py            # Azure Cost Management
│       ├── digitalocean.py     # DigitalOcean Billing API
│       ├── pricing.py          # Comparador de preços (APIs públicas)
│       └── local.py            # psutil + libvirt KVM
├── frontend/
│   └── index.html              # Dashboard (HTML/CSS/JS puro)
├── .env.example                # Template de variáveis de ambiente
├── install.sh                  # Script de instalação
└── README.md
```

---

## ⚙️ Pré-requisitos

| Requisito | Versão mínima |
|-----------|--------------|
| Ubuntu | 24 LTS |
| Python | 3.12+ |
| KVM/libvirt | qualquer |
| Nginx | qualquer |
| Tailscale | qualquer (para CI/CD remoto) |

Contas nas clouds que deseja monitorar: **AWS**, **GCP**, **OCI**, **Azure**, **DigitalOcean**.

---

## 🚀 Instalação

### 1. Clone o repositório

```bash
git clone https://github.com/JustoDaniel/infradash.git
cd infradash
```

### 2. Configure as variáveis de ambiente

```bash
cp .env.example .env
nano .env
```

Preencha com suas credenciais (veja a seção [Credenciais por Cloud](#-credenciais-por-cloud) abaixo).

### 3. Execute o instalador

```bash
sudo bash install.sh
```

O script cuida de tudo:
- Instala dependências do sistema (`python3`, `nginx`, `libvirt`, etc.)
- Cria o usuário de serviço `infradash`
- Configura o `virtualenv` com todas as libs Python
- Cria e habilita o serviço `systemd`
- Configura o Nginx como proxy reverso na porta 80

### 4. Acesse o dashboard

```
http://IP-DA-SUA-MAQUINA
```

---

## 🔍 Comparador de Preços

O InfraDash inclui um comparador de preços em tempo real que busca preços reais de instâncias compute diretamente das APIs públicas de cada cloud — sem necessidade de credenciais.

Configure os sliders de **vCPU**, **RAM** e **horas/mês** e veja instantaneamente qual cloud oferece o melhor preço para aquela configuração, com o tipo de instância equivalente em cada provider.

| Cloud | API de Pricing | Região base |
|-------|---------------|-------------|
| AWS | Price List API | us-east-1 |
| GCP | Cloud Billing Catalog API | us-east1 |
| Azure | Retail Prices API | eastus |
| OCI | Pricing API | us-ashburn-1 |
| DigitalOcean | Droplets Pricing (tabela oficial) | nyc3 |

> Os preços são cacheados por **24h** — mudam raramente e o cache evita requisições desnecessárias.

---

## 🔑 Credenciais por Cloud

### AWS

1. Acesse **IAM → Users → Create User**
2. Nome sugerido: `infradash-readonly`
3. Anexe a policy: `AWSBillingReadOnlyAccess` + `ReadOnlyAccess`
4. Gere uma **Access Key** (tipo: *Application running outside AWS*)
5. Preencha no `.env`:

```env
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
AWS_DEFAULT_REGION=us-east-1
```

### GCP

1. Acesse **IAM → Service Accounts → Create**
2. Nome sugerido: `infradash-sa`
3. Atribua o papel: **Billing Account Viewer**
4. Gere uma chave JSON e salve em `/opt/infradash/gcp-credentials.json`
5. Preencha no `.env`:

```env
GCP_PROJECT_ID=seu-projeto-id
GCP_CREDENTIALS_PATH=/opt/infradash/gcp-credentials.json
```

### OCI

1. Acesse **Identity → Users → seu usuário → API Keys → Add**
2. Gere o par de chaves e salve a chave privada em `/opt/infradash/oci_api_key.pem`
3. Preencha no `.env`:

```env
OCI_USER_OCID=ocid1.user.oc1..xxxxx
OCI_TENANCY_OCID=ocid1.tenancy.oc1..xxxxx
OCI_REGION=sa-saopaulo-1
OCI_FINGERPRINT=xx:xx:xx:xx:xx
OCI_KEY_FILE=/opt/infradash/oci_api_key.pem
```

> ⚠️ **Nunca versione os arquivos `.env`, `.json` ou `.pem`** — o `.gitignore` já os bloqueia por padrão.

### Azure

1. Instale o **Azure CLI**: `curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash`
2. Faça login: `az login`
3. Crie o Service Principal com permissão de leitura:

```bash
az ad sp create-for-rbac \
  --name "infradash-readonly" \
  --role "Billing Reader" \
  --scopes "/subscriptions/SUA_SUBSCRIPTION_ID"
```

4. Instale a lib no venv:

```bash
sudo /opt/infradash/venv/bin/pip install azure-mgmt-costmanagement azure-identity
```

5. Preencha no `.env` com os valores retornados pelo comando acima:

```env
AZURE_CLIENT_ID=appId-retornado
AZURE_CLIENT_SECRET=password-retornado
AZURE_TENANT_ID=tenant-retornado
AZURE_SUBSCRIPTION_ID=sua-subscription-id
```

> ⚠️ **Nunca versione os arquivos `.env`, `.json` ou `.pem`** — o `.gitignore` já os bloqueia por padrão.

---

## 🔄 CI/CD com GitHub Actions + Tailscale

1. Acesse **cloud.digitalocean.com → API → Tokens**
2. Clique em **Generate New Token**
3. Nome sugerido: `infradash-readonly`
4. Marque apenas **Read** (sem Write)
5. Preencha no `.env`:

```env
DIGITALOCEAN_TOKEN=seu_token_aqui
```

> ⚠️ **Nunca versione os arquivos `.env`, `.json` ou `.pem`** — o `.gitignore` já os bloqueia por padrão.

A esteira faz deploy automático no seu servidor toda vez que você faz `git push` na branch `main`.

### Como funciona

```
git push → GitHub Actions (ubuntu-latest)
              │
              ├─ 1. Checkout do código
              ├─ 2. Conecta ao Tailscale (acesso privado ao servidor)
              ├─ 3. Configura chave SSH
              ├─ 4. rsync dos arquivos → /opt/infradash
              └─ 5. systemctl restart infradash
```

### Passo a passo para configurar

#### 1. Instale o Tailscale no servidor

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Anote o IP Tailscale da máquina (ex: `100.x.x.x`).

#### 2. Instale o SSH Server

```bash
sudo apt install openssh-server -y
sudo systemctl enable --now ssh
```

#### 3. Crie uma chave SSH dedicada para o GitHub Actions

```bash
ssh-keygen -t ed25519 -C "github-actions-infradash" \
  -f ~/.ssh/github_actions_infradash -N ""

cat ~/.ssh/github_actions_infradash.pub >> ~/.ssh/authorized_keys
```

#### 4. Configure o sudo sem senha para o restart

```bash
echo "SEU_USUARIO ALL=(ALL) NOPASSWD: /bin/systemctl restart infradash, /bin/systemctl status infradash" \
  | sudo tee /etc/sudoers.d/infradash-deploy
```

#### 5. Gere uma Tailscale Auth Key

1. Acesse **login.tailscale.com → Settings → Keys**
2. Clique em **Generate auth key**
3. Marque: ✅ **Reusable** e ✅ **Ephemeral**

#### 6. Adicione os Secrets no GitHub

Vá em **github.com/SEU_USUARIO/infradash → Settings → Secrets and variables → Actions**:

| Secret | Valor |
|--------|-------|
| `SSH_PRIVATE_KEY` | Conteúdo de `~/.ssh/github_actions_infradash` |
| `SSH_HOST` | IP Tailscale do servidor (ex: `100.x.x.x`) |
| `SSH_USER` | Seu usuário Linux (ex: `justo`) |
| `TAILSCALE_AUTHKEY` | Auth key gerada no passo anterior |

#### 7. Faça o primeiro push

```bash
git add .
git commit -m "ci: configure GitHub Actions deploy"
git push
```

Acompanhe em tempo real em **github.com/SEU_USUARIO/infradash → Actions** ✅

---

## 🛠️ Comandos úteis

```bash
# Ver status do serviço
sudo systemctl status infradash

# Ver logs em tempo real
sudo journalctl -u infradash -f

# Reiniciar manualmente
sudo systemctl restart infradash

# Editar credenciais
sudo nano /opt/infradash/.env
```

---

## 📊 Consumo de recursos

| Componente | CPU | RAM |
|-----------|-----|-----|
| Gunicorn (2 workers) | ~0.1% | ~60 MB |
| Nginx | ~0.0% | ~10 MB |
| **Total** | **< 1%** | **~70 MB** |

Cache de 1h nas APIs cloud evita custos desnecessários de requisição.

---

## 🗺️ Roadmap

- [ ] Alertas por e-mail/Telegram quando custo ultrapassar limite
- [ ] HTTPS com Let's Encrypt (`infra.seudominio.com.br`)
- [x] Suporte a Azure ✅
- [x] Suporte a DigitalOcean ✅
- [x] Comparador de preços entre clouds em tempo real ✅
- [ ] Histórico de custos com gráfico de tendência
- [ ] Autenticação básica para acesso externo

---

## 📄 Licença

MIT © [JustoDaniel](https://github.com/JustoDaniel)

---

<div align="center">
  <sub>Feito com ☕ e muita curiosidade por um sysadmin que não consegue parar de otimizar o homelab.</sub>
</div>

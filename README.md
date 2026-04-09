# InfraDash — Setup Guide

## 1. Instalação rápida

```bash
git clone <repo> infradash   # ou copie os arquivos
cd infradash
sudo bash install.sh
```

## 2. Credenciais — o que configurar

Edite `/opt/infradash/.env` após a instalação.

---

### AWS

1. No console AWS → IAM → Users → Create User
2. Permissões mínimas necessárias (attach policies):
   - `AWSBillingReadOnlyAccess`
   - `ReadOnlyAccess` (ou `AmazonEC2ReadOnlyAccess` se quiser só EC2)
3. Security credentials → Create access key → "Other"
4. Copie `Access Key ID` e `Secret Access Key` no `.env`

---

### GCP

1. Console GCP → IAM & Admin → Service Accounts → Create
2. Roles a adicionar:
   - `Billing Account Viewer`
   - `Viewer`
3. Keys → Add Key → JSON → Baixar o arquivo
4. Copie o JSON para `/opt/infradash/gcp-credentials.json`
5. No `.env`: `GCP_CREDENTIALS_PATH=/opt/infradash/gcp-credentials.json`
6. Habilite a API:
   ```bash
   gcloud services enable cloudbilling.googleapis.com
   ```

---

### OCI

**Opção A — config interativo (recomendado para começar):**
```bash
oci setup config
# Siga as instruções, salva em ~/.oci/config
# O collector usa esse arquivo automaticamente se .env não tiver as vars
```

**Opção B — via .env:**
1. User OCID: Console OCI → Profile → User settings → OCID
2. Tenancy OCID: Administration → Tenancy Details → OCID
3. Gere uma API Key: User settings → API Keys → Add API Key
4. Copie a chave privada para `/opt/infradash/oci_api_key.pem`
5. Preencha fingerprint, region no `.env`

Política necessária (adicione no tenancy como admin):
```
allow group InfraDash to read usage-reports in tenancy
allow group InfraDash to read cost-reports in tenancy
```

---

## 3. Verificar se está rodando

```bash
# Status do serviço
sudo systemctl status infradash

# Testar API
curl http://localhost/api/health
curl http://localhost/api/summary | python3 -m json.tool

# Logs
sudo journalctl -u infradash -f
tail -f /opt/infradash/logs/error.log
```

## 4. Acesso externo (futuro — justodaniel.com.br)

Quando quiser expor:

```bash
# 1. Aponte infra.justodaniel.com.br → IP da sua máquina no DNS
# 2. Edite /etc/nginx/sites-available/infradash:
#    server_name infra.justodaniel.com.br;
# 3. Instale Certbot e gere HTTPS:
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d infra.justodaniel.com.br
# 4. Recarregue nginx
sudo systemctl reload nginx
```

## 5. Consumo de recursos esperado

| Componente | CPU | RAM |
|-----------|-----|-----|
| Gunicorn (2 workers) | ~0.1% | ~60 MB |
| Nginx | ~0% | ~10 MB |
| **Total** | **< 1%** | **~70 MB** |

Cache de 1h para APIs cloud garante custo zero de requisições desnecessárias.

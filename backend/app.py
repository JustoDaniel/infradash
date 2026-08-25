"""
InfraDash — Backend API
Flask + Gunicorn | coleta dados de GCP, AWS, OCI, Azure e KVM local
"""

import os, time, json, threading, uuid
from pathlib import Path
from flask import Flask, jsonify, request
from dotenv import load_dotenv
from .collectors.azure import get_costs as collect_azure
from .collectors.aws import collect_aws
from .collectors.gcp import collect_gcp, load_config as _load_gcp_config, CONFIG_PATH as _GCP_CONFIG_PATH
from .collectors.oci import collect_oci
from .collectors.digitalocean import collect_digitalocean
from .collectors.local import collect_local
from .collectors.pricing import compare_prices

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")

# ── Cache simples em memória ──────────────────────────────────
_cache: dict = {}
_lock = threading.Lock()

CACHE_TTL_CLOUD = int(os.getenv("CACHE_TTL_CLOUD", 3600))
CACHE_TTL_LOCAL = int(os.getenv("CACHE_TTL_LOCAL", 30))


def get_cached(key: str, ttl: int, collector_fn):
    """Retorna dado do cache ou chama o collector e armazena."""
    with _lock:
        entry = _cache.get(key)
        if entry and (time.time() - entry["ts"]) < ttl:
            return entry["data"]
    try:
        data = collector_fn()
    except Exception as e:
        data = {"error": str(e), "provider": key}
    with _lock:
        _cache[key] = {"ts": time.time(), "data": data}
    return data


# ── Rotas ─────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "ts": time.time()})


@app.route("/api/summary")
def summary():
    """Retorna todos os dados de uma vez (cloud + local)."""
    aws   = get_cached("aws",   CACHE_TTL_CLOUD, collect_aws)
    gcp   = get_cached("gcp",   CACHE_TTL_CLOUD, collect_gcp)
    oci   = get_cached("oci",   CACHE_TTL_CLOUD, collect_oci)
    azure = get_cached("azure", CACHE_TTL_CLOUD, collect_azure)
    do    = get_cached("do",    CACHE_TTL_CLOUD, collect_digitalocean)
    local = get_cached("local", CACHE_TTL_LOCAL, collect_local)

    return jsonify({
        "cloud": [aws, gcp, oci, azure, do],
        "local": local,
        "ts": time.time(),
    })


@app.route("/api/cloud")
def cloud_only():
    aws   = get_cached("aws",   CACHE_TTL_CLOUD, collect_aws)
    gcp   = get_cached("gcp",   CACHE_TTL_CLOUD, collect_gcp)
    oci   = get_cached("oci",   CACHE_TTL_CLOUD, collect_oci)
    azure = get_cached("azure", CACHE_TTL_CLOUD, collect_azure)
    do    = get_cached("do",    CACHE_TTL_CLOUD, collect_digitalocean)
    return jsonify([aws, gcp, oci, azure, do])
    


@app.route("/api/local")
def local_only():
    return jsonify(get_cached("local", CACHE_TTL_LOCAL, collect_local))


@app.route("/api/cache/clear", methods=["POST"])
def clear_cache():
    with _lock:
        _cache.clear()
    return jsonify({"cleared": True})

@app.route("/api/pricing")
def pricing():
    """Compara preços de instâncias entre clouds."""
    try:
        vcpu  = int(request.args.get("vcpu", 4))
        mem   = int(request.args.get("mem", 16))
        hours = int(request.args.get("hours", 730))
        vcpu  = max(1, min(vcpu, 64))
        mem   = max(1, min(mem, 512))
        hours = max(1, min(hours, 744))
        data = compare_prices(vcpu, mem, hours)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Admin: GCP Billing Config ─────────────────────────────────

def _save_gcp_config(config: dict):
    with open(_GCP_CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


@app.route("/api/admin/gcp", methods=["GET"])
def admin_gcp_get():
    """Retorna a configuração atual de billings GCP."""
    return jsonify(_load_gcp_config())


@app.route("/api/admin/gcp/credentials", methods=["PUT"])
def admin_gcp_credentials():
    """Atualiza o caminho do arquivo de service account."""
    data = request.json or {}
    cred_path = data.get("credentials_path", "").strip()
    if cred_path and not Path(cred_path).is_file():
        return jsonify({"error": f"Arquivo não encontrado: {cred_path}"}), 400
    config = _load_gcp_config()
    config["credentials_path"] = cred_path
    _save_gcp_config(config)
    with _lock:
        _cache.pop("gcp", None)
    return jsonify({"ok": True})


@app.route("/api/admin/gcp/billings", methods=["POST"])
def admin_gcp_add():
    """Adiciona uma billing account GCP à configuração."""
    data = request.json or {}
    required = ["name", "billing_account_id", "project_id"]
    missing = [k for k in required if not data.get(k, "").strip()]
    if missing:
        return jsonify({"error": f"Campos obrigatórios: {missing}"}), 400

    # Credencial específica desta billing (opcional — sobrepõe a global)
    billing_cred = data.get("credentials_path", "").strip()
    if billing_cred and not Path(billing_cred).is_file():
        return jsonify({"error": f"Arquivo de credenciais não encontrado: {billing_cred}"}), 400

    config = _load_gcp_config()
    entry = {
        "id":                 str(uuid.uuid4())[:8],
        "name":               data["name"].strip(),
        "billing_account_id": data["billing_account_id"].strip().upper(),
        "project_id":         data["project_id"].strip(),
        "dataset":            data.get("dataset", "gcp_billing_data").strip() or "gcp_billing_data",
        "credentials_path":   billing_cred or None,
        "enabled":            True,
    }
    config["billings"].append(entry)
    _save_gcp_config(config)
    with _lock:
        _cache.pop("gcp", None)
    return jsonify(entry), 201


@app.route("/api/admin/gcp/billings/<billing_id>", methods=["PUT"])
def admin_gcp_update(billing_id):
    """Atualiza (enable/disable ou rename) uma billing account."""
    data = request.json or {}
    config = _load_gcp_config()
    for b in config["billings"]:
        if b["id"] == billing_id:
            if "enabled" in data:
                b["enabled"] = bool(data["enabled"])
            if "name" in data and data["name"].strip():
                b["name"] = data["name"].strip()
    _save_gcp_config(config)
    with _lock:
        _cache.pop("gcp", None)
    return jsonify({"ok": True})


@app.route("/api/admin/gcp/billings/<billing_id>", methods=["DELETE"])
def admin_gcp_delete(billing_id):
    """Remove uma billing account da configuração."""
    config = _load_gcp_config()
    config["billings"] = [b for b in config["billings"] if b["id"] != billing_id]
    _save_gcp_config(config)
    with _lock:
        _cache.pop("gcp", None)
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True, port=8765)

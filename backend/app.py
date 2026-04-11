"""
InfraDash — Backend API
Flask + Gunicorn | coleta dados de GCP, AWS, OCI, Azure e KVM local
"""

import os, time, json, threading
from flask import Flask, jsonify, request
from dotenv import load_dotenv
from .collectors.azure import get_costs as collect_azure
from .collectors.aws import collect_aws
from .collectors.gcp import collect_gcp
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


if __name__ == "__main__":
    app.run(debug=True, port=8765)

# ============================================================
# Tookie-OSINT API Wrapper
# Transforma o Tookie-OSINT (CLI) em API REST para o Blitz 360
# ============================================================

import os
import sys
import json
import subprocess
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Permite chamadas do Blitz 360

# Versão da API
API_VERSION = "1.0.0"

# ============================================================
# ROTA RAIZ — Health check (para o Render saber que está OK)
# ============================================================
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "service": "Tookie-OSINT API",
        "version": API_VERSION,
        "status": "online",
        "endpoints": {
            "POST /search": "Busca por nome e cidade",
            "GET /health": "Status da API"
        }
    })

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "version": API_VERSION})


# ============================================================
# ROTA PRINCIPAL — /search
# Recebe: { "name": "Max Növara", "city": "Uberlândia" }
# Retorna: JSON com perfis encontrados
# ============================================================
@app.route("/search", methods=["POST", "OPTIONS"])
def search():
    if request.method == "OPTIONS":
        return "", 200

    try:
        data = request.get_json(force=True) or {}
    except Exception as e:
        return jsonify({"error": "JSON inválido", "detail": str(e)}), 400

    name = (data.get("name") or "").strip()
    city = (data.get("city") or "").strip()

    if not name:
        return jsonify({"error": "Parâmetro 'name' obrigatório"}), 400

    # Monta comando do Tookie
    # Formato esperado: tookie --name "X" --city "Y"
    cmd = [sys.executable, "-m", "tookie", "--name", name]
    if city:
        cmd.extend(["--city", city])

    try:
        # Executa o Tookie com timeout de 60s
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )

        stdout = result.stdout or ""
        stderr = result.stderr or ""

        # Tenta extrair JSON da saída (Tookie pode retornar texto)
        accounts = parse_tookie_output(stdout)

        return jsonify({
            "success": True,
            "name": name,
            "city": city,
            "accounts": accounts,
            "raw_output": stdout[:2000] if not accounts else None,
            "stderr": stderr[:500] if stderr else None
        })

    except subprocess.TimeoutExpired:
        return jsonify({
            "success": False,
            "error": "Tempo esgotado (60s). Tente novamente."
        }), 504
    except Exception as e:
        return jsonify({
            "success": False,
            "error": "Falha ao executar Tookie",
            "detail": str(e)
        }), 500


# ============================================================
# Parser do output do Tookie
# ============================================================
def parse_tookie_output(output):
    """Extrai contas/perfis do output do Tookie"""
    accounts = []

    if not output:
        return accounts

    # Tenta JSON primeiro
    try:
        data = json.loads(output)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "results" in data:
            return data["results"]
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: busca URLs de redes sociais no texto
    import re
    url_pattern = r'https?://(?:www\.)?(instagram\.com|twitter\.com|x\.com|tiktok\.com|facebook\.com|linkedin\.com|youtube\.com|github\.com)/[^\s"\'<>]+'
    urls = re.findall(url_pattern, output)
    full_urls = re.findall(r'https?://[^\s"\'<>]+', output)

    seen = set()
    for url in full_urls:
        url = url.rstrip(".,;")
        if url in seen:
            continue
        seen.add(url)

        platform = "unknown"
        if "instagram" in url: platform = "instagram"
        elif "twitter" in url or "x.com" in url: platform = "twitter"
        elif "tiktok" in url: platform = "tiktok"
        elif "facebook" in url: platform = "facebook"
        elif "linkedin" in url: platform = "linkedin"
        elif "youtube" in url: platform = "youtube"
        elif "github" in url: platform = "github"

        accounts.append({
            "platform": platform,
            "url": url,
            "username": url.rstrip("/").split("/")[-1]
        })

    return accounts


# ============================================================
# Inicialização
# ============================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

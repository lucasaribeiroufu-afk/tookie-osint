# ============================================================
# Tookie-OSINT API Wrapper (v2)
# Chama o brib.py corretamente e retorna JSON
# ============================================================

import os
import sys
import json
import glob
import time
import subprocess
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

API_VERSION = "2.0.0"
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))


# ============================================================
# ROTA RAIZ - Health check
# ============================================================
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "service": "Tookie-OSINT API",
        "version": API_VERSION,
        "status": "online",
        "endpoints": {
            "POST /search": "Busca por username",
            "GET /health": "Status"
        }
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "version": API_VERSION})


# ============================================================
# ROTA /search
# Body: { "name": "alfred" }
# Retorna JSON com resultados
# ============================================================
@app.route("/search", methods=["POST", "OPTIONS"])
def search():
    if request.method == "OPTIONS":
        return "", 200

    try:
        data = request.get_json(force=True) or {}
    except Exception as e:
        return jsonify({"error": "JSON invalido", "detail": str(e)}), 400

    name = (data.get("name") or "").strip().replace(" ", "")

    if not name:
        return jsonify({"error": "Parametro 'name' obrigatorio"}), 400

    # Snapshot de arquivos antes da execucao
    before_files = set(glob.glob(os.path.join(REPO_ROOT, "*.json")))

    # Comando correto do Tookie (script mode, JSON output)
    cmd = [
        sys.executable, "brib.py",
        "-u", name,
        "-sC",       # modo script (sem UI)
        "-o", "json" # saida JSON
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=REPO_ROOT,
            env={**os.environ, "PYTHONUNBUFFERED": "1"}
        )

        stdout = result.stdout or ""
        stderr = result.stderr or ""

        # Procura arquivo JSON novo criado
        time.sleep(0.5)
        after_files = set(glob.glob(os.path.join(REPO_ROOT, "*.json")))
        new_files = list(after_files - before_files)

        accounts = []

        # Tenta ler arquivo novo
        for f in new_files:
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    content = fh.read()
                    parsed = json.loads(content)
                    if isinstance(parsed, list):
                        accounts.extend(parsed)
                    elif isinstance(parsed, dict):
                        accounts.append(parsed)
            except Exception:
                pass

        # Fallback: parse do stdout
        if not accounts and stdout:
            accounts = parse_text_output(stdout)

        return jsonify({
            "success": True,
            "name": name,
            "accounts": accounts,
            "total_found": len(accounts),
            "stderr_snippet": stderr[:300] if stderr else None
        })

    except subprocess.TimeoutExpired:
        return jsonify({
            "success": False,
            "error": "Timeout (120s)"
        }), 504
    except Exception as e:
        return jsonify({
            "success": False,
            "error": "Erro ao executar",
            "detail": str(e)
        }), 500


def parse_text_output(output):
    """Extrai URLs de redes sociais do texto"""
    import re
    accounts = []
    seen = set()

    patterns = {
        "instagram": r'https?://(?:www\.)?instagram\.com/[\w.\-]+',
        "twitter": r'https?://(?:www\.)?(?:twitter|x)\.com/[\w.\-]+',
        "tiktok": r'https?://(?:www\.)?tiktok\.com/@[\w.\-]+',
        "facebook": r'https?://(?:www\.)?facebook\.com/[\w.\-]+',
        "linkedin": r'https?://(?:www\.)?linkedin\.com/in/[\w.\-]+',
        "github": r'https?://(?:www\.)?github\.com/[\w.\-]+',
        "youtube": r'https?://(?:www\.)?youtube\.com/@[\w.\-]+',
    }

    for platform, pattern in patterns.items():
        urls = re.findall(pattern, output)
        for url in urls:
            url = url.rstrip(".,;)\"'")
            if url in seen:
                continue
            seen.add(url)
            accounts.append({
                "platform": platform,
                "url": url,
                "username": url.rstrip("/").split("/")[-1]
            })

    return accounts


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

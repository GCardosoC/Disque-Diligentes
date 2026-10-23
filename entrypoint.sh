#!/bin/sh
set -e

echo "=========================================================="
echo "  Disque Diligentes - Iniciando no Render"
echo "=========================================================="

# 1. Porta interna isolada para o motor do Google Maps (não exposta externamente)
export GMAPS_PORT="8089"

# Identifica o binário do motor (no Linux da imagem Docker usa hífen: google-maps-scraper)
if command -v google-maps-scraper >/dev/null 2>&1; then
    GMAPS_BIN="google-maps-scraper"
elif command -v google_maps_scraper >/dev/null 2>&1; then
    GMAPS_BIN="google_maps_scraper"
elif [ -f "/google-maps-scraper" ]; then
    GMAPS_BIN="/google-maps-scraper"
else
    GMAPS_BIN="google-maps-scraper"
fi

# Inicia o motor do Google Maps Scraper em background em 127.0.0.1:8089
echo "[1/2] Iniciando motor do Google Maps Scraper ($GMAPS_BIN) em 127.0.0.1:${GMAPS_PORT}..."
mkdir -p /gmapsdata
$GMAPS_BIN -web -addr "127.0.0.1:${GMAPS_PORT}" -data-folder /gmapsdata &

# Aguarda 2 segundos para o motor inicializar
sleep 2

# 2. Inicia o Servidor Publico do Disque Diligentes na porta do Render ($PORT ou 8080)
PUBLIC_PORT="${PORT:-8080}"
echo "[2/2] Iniciando Servidor Disque Diligentes na porta ${PUBLIC_PORT} (Host: 0.0.0.0)..."
export PORT="${PUBLIC_PORT}"
export HOST="0.0.0.0"
exec python3 /app/server_local.py

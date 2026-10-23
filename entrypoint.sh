#!/bin/sh
set -e

echo "=========================================================="
echo "  Disque Diligentes - Iniciando no Render"
echo "=========================================================="

# 1. Inicia o motor do Google Maps Scraper em background na porta 8080
echo "[1/2] Iniciando motor do Google Maps Scraper na porta 8080..."
mkdir -p /gmapsdata
google_maps_scraper -web -data-folder /gmapsdata &

# Aguarda 2 segundos para o motor inicializar
sleep 2

# 2. Inicia o Servidor Python público na porta do Render ($PORT)
echo "[2/2] Iniciando Servidor Disque Diligentes na porta ${PORT:-10000} (Host: ${HOST:-0.0.0.0})..."
exec python3 server_local.py

# ------------------------------------------------------------------------------
# Dockerfile para Render.com / Nuvem
# Aplicação: Disque Diligentes (Extrator Web + Google Maps Scraper + WhatsApp)
# ------------------------------------------------------------------------------
FROM gosom/google-maps-scraper:v1.18.1

USER root

# Instala Python 3 e utilitários essenciais
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia os arquivos da aplicação
COPY index.html ./index.html
COPY server_local.py ./server_local.py
COPY cidades_brasil.json ./cidades_brasil.json
COPY coordenadas_cidades.json ./coordenadas_cidades.json
COPY entrypoint.sh ./entrypoint.sh

# Garante permissão de execução no script de entrada
RUN chmod +x ./entrypoint.sh

# Porta pública exposta para o Render
ENV PORT=8080
ENV HOST=0.0.0.0

EXPOSE 8080
EXPOSE 10000

# Sobrescreve o ENTRYPOINT da imagem base (que executava apenas o google-maps-scraper)
ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]

# ------------------------------------------------------------------------------
# Dockerfile para Render.com / Nuvem (Diretório extrator_netlify)
# ------------------------------------------------------------------------------
FROM gosom/google-maps-scraper:v1.18.1

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY index.html ./index.html
COPY server_local.py ./server_local.py
COPY cidades_brasil.json ./cidades_brasil.json
COPY coordenadas_cidades.json ./coordenadas_cidades.json
COPY entrypoint.sh ./entrypoint.sh

RUN chmod +x ./entrypoint.sh

ENV PORT=10000
ENV HOST=0.0.0.0

EXPOSE 10000

CMD ["./entrypoint.sh"]

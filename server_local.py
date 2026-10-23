import os
import re
import sys
import json
import html
import math
import socket
import ipaddress
import threading
import subprocess
import unicodedata
import urllib.request
import urllib.parse
from urllib.parse import urljoin, urlparse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

PORT = int(os.environ.get("PORT", 8000))
HOST = os.environ.get("HOST", "127.0.0.1")
APP_ACCESS_TOKEN = os.environ.get("APP_ACCESS_TOKEN", "").strip()
GMAPS_PORT = int(os.environ.get("GMAPS_PORT", 8080))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://correspondentesnaweb.com.br/"
}

ROTAS_IGNORAR = [
    "/login", "/cadastr", "/sobre", "/contato", "/sistema", "/termos", 
    "/politica", "/privacidade", "/planos", "/anuncie", "/faq", "/ajuda", 
    "/blog", "/noticias", "/feed", "/wp-", "/tag/", "/category/", "/cart",
    "/carrinho", "/checkout", "/minha-conta", "/esqueci", "/recuperar", "/senha"
]

def validar_url_segura(url_str, resolver_dns=False):
    if not url_str or not isinstance(url_str, str) or len(url_str) > 2048:
        return False
    try:
        u = urlparse(url_str)
        if u.scheme not in ["http", "https"]:
            return False
        if u.username or u.password:
            return False
        if u.port not in (None, 80, 443):
            return False
        host = (u.hostname or "").lower()
        if not host or "." not in host or host.startswith(".") or host.endswith("."):
            return False
        if host in ["localhost", "0.0.0.0", "::1"] or host.startswith("[") or ":" in host:
            return False
        tlds_internos = (
            ".localhost", ".local", ".internal", ".lan", ".home", ".arpa",
            ".corp", ".intranet", ".nip.io", ".sslip.io", ".xip.io",
            ".localtest.me", ".lvh.me", ".vcap.me"
        )
        if host.endswith(tlds_internos):
            return False
        tld = host.rsplit(".", 1)[-1]
        if not re.match(r"^[a-z]{2,24}$", tld):
            return False
        if (
            host.startswith("127.") or
            host.startswith("10.") or
            host.startswith("192.168.") or
            host.startswith("169.254.") or
            host.startswith("0.") or
            re.search(r"(?:^|\.)(?:127\.\d+\.\d+\.\d+|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|169\.254\.\d+\.\d+)(?:\.|$)", host) or
            re.match(r"^100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.", host) or
            re.match(r"^198\.1[89]\.", host) or
            re.match(r"^172\.(1[6-9]|2\d|3[01])\.", host)
        ):
            return False
        if resolver_dns:
            ips = socket.getaddrinfo(host, None)
            for _, _, _, _, sockaddr in ips:
                ip_obj = ipaddress.ip_address(sockaddr[0])
                if (
                    ip_obj.is_private or
                    ip_obj.is_loopback or
                    ip_obj.is_link_local or
                    ip_obj.is_reserved or
                    ip_obj.is_multicast or
                    ip_obj.is_unspecified
                ):
                    return False
        return True
    except Exception:
        return False

class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Impede que redirecionamentos HTTP (301/302/307/308) escapem para IPs internos, loopback ou não autorizados."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        full_new_url = urljoin(req.full_url, newurl)
        if not validar_url_segura(full_new_url, resolver_dns=True):
            raise urllib.error.HTTPError(full_new_url, 400, "Redirecionamento para endereço não autorizado bloqueado.", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, full_new_url)

SAFE_OPENER = urllib.request.build_opener(SafeRedirectHandler)

def limpar_html(tag_str, max_len=200):
    if not tag_str or not isinstance(tag_str, str):
        return ""
    sem_tags = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", tag_str)).strip()
    decodificado = html.unescape(sem_tags)
    higienizado = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]+", " ", re.sub(r"[<>]", "", decodificado))).strip()
    return higienizado[:max_len] if max_len > 0 else higienizado

class TelefoneItem(dict):
    """
    Representação estruturada de telefone para a API/JSON,
    mantendo compatibilidade com código/testes que esperam string ou dicionário.
    """
    def __init__(self, numero_formatado, numero_limpo, tipo, eh_whatsapp):
        super().__init__(
            numero_formatado=numero_formatado,
            numero_limpo=numero_limpo,
            tipo=tipo,
            eh_whatsapp=eh_whatsapp
        )

    def __str__(self):
        return self["numero_formatado"]

    def __repr__(self):
        return super().__repr__()

    def __eq__(self, other):
        if isinstance(other, str):
            return self["numero_formatado"] == other or self["numero_limpo"] == other
        if isinstance(other, dict):
            return self.get("numero_limpo") == other.get("numero_limpo")
        return super().__eq__(other)

    def __hash__(self):
        return hash(self["numero_limpo"])

    def startswith(self, prefix, *args):
        return self["numero_formatado"].startswith(prefix, *args)

    def endswith(self, suffix, *args):
        return self["numero_formatado"].endswith(suffix, *args)

    def __contains__(self, item):
        if isinstance(item, str):
            return item in self["numero_formatado"] or super().__contains__(item)
        return super().__contains__(item)

    def __lt__(self, other):
        tipo_peso = {"celular": 0, "fixo": 1}
        peso_self = tipo_peso.get(self.get("tipo"), 2)
        if isinstance(other, dict):
            peso_other = tipo_peso.get(other.get("tipo"), 2)
            if peso_self != peso_other:
                return peso_self < peso_other
            return self.get("numero_formatado", "") < other.get("numero_formatado", "")
        if isinstance(other, str):
            return self["numero_formatado"] < other
        return False

def validar_telefones(texto_html):
    if not texto_html or not isinstance(texto_html, str):
        return []
    candidatos = []

    # 1. Links tel: (captura atributo href e texto interno da tag <a> se houver)
    for m in re.finditer(r'<a\b[^>]*?\bhref\s*=\s*["\']tel:([^"\']+)["\'][^>]*>([\s\S]*?)</a>', texto_html, re.I):
        candidatos.append(m.group(1))
        candidatos.append(m.group(2))
    for l in re.findall(r'href\s*=\s*["\']tel:([^"\']+)["\']', texto_html, re.I):
        candidatos.append(l)

    # 2. Links WhatsApp (wa.me e whatsapp.com/send)
    for w in re.findall(r'(?:wa\.me/|whatsapp\.com/send/?\?(?:[^"\'\s>]*&)?phone=)\+?(\d{10,13})', texto_html, re.I):
        candidatos.append(w)

    # 3. Padrão com parênteses: (XX) XXXXX-XXXX, (0XX) XXXXX-XXXX, (XX) 9 XXXX-XXXX ou (XX) XXXX-XXXX
    for m in re.finditer(r"\((0?[1-9]{2})\)\s*(9?[\s.]?\d{4})[-\s.]?(\d{4})", texto_html):
        candidatos.append(m.group(0))

    # 4. Padrão com DDD sem parênteses: +55 XX 9XXXX-XXXX, +55XX9XXXXXXXX, 0XX 9XXXX-XXXX ou XX 9XXXX-XXXX
    for m in re.finditer(r"(?:^|[^\d])(?:\+?55[\s.-]*)?(0?[1-9]{2})[\s.-]*(9?[\s.]?\d{4})[-\s.]?(\d{4})(?!\d)", texto_html):
        candidatos.append(f"{m.group(1)}{m.group(2)}{m.group(3)}")

    # 5. Seção de contato ou linhas com 'tel' ou 'cel'
    for linha in texto_html.splitlines():
        if any(k in linha.lower() for k in ["contato", "telefone", "celular", "tel:", "whatsapp"]):
            for num_seq in re.findall(r"\b(?:\+?55\s*)?(?:0?[1-9]{2}\s*)?9?[\s.]?\d{4}[-\s.]?\d{4}\b", linha):
                candidatos.append(num_seq)

    itens = {}
    for item in candidatos:
        digitos = re.sub(r"\D", "", str(item))
        # Remove DDI 55 se vier com 12 ou 13 dígitos
        if digitos.startswith("55") and len(digitos) in [12, 13]:
            digitos = digitos[2:]
        # Remove 0 inicial de DDD se vier com 11 ou 12 dígitos (ex: 011...)
        if digitos.startswith("0") and len(digitos) in [11, 12]:
            digitos = digitos[1:]

        # Deve ter 10 dígitos (fixo) ou 11 dígitos (celular)
        if len(digitos) in [10, 11]:
            ddd = int(digitos[:2])
            if 11 <= ddd <= 99:
                # Rejeita repetições falsas (ex: 99999-9999 ou 1111-1111)
                if len(set(digitos[2:])) <= 1:
                    continue

                if len(digitos) == 11:
                    # No Brasil, celular de 9 dígitos sempre inicia com 9 após DDD
                    if digitos[2] != '9':
                        continue
                    tipo = "celular"
                    eh_whatsapp = True
                    fmt = f"({digitos[:2]}) {digitos[2:7]}-{digitos[7:]}"
                else:
                    # Telefone fixo (8 dígitos após DDD)
                    tipo = "fixo"
                    eh_whatsapp = False
                    fmt = f"({digitos[:2]}) {digitos[2:6]}-{digitos[6:]}"

                numero_limpo = f"55{digitos}"
                if numero_limpo not in itens:
                    itens[numero_limpo] = TelefoneItem(
                        numero_formatado=fmt,
                        numero_limpo=numero_limpo,
                        tipo=tipo,
                        eh_whatsapp=eh_whatsapp
                    )

    # Ordena: celulares/WhatsApp no topo, fixos ao final
    return sorted(list(itens.values()))

def extrair_emails(texto_html):
    if not texto_html or not isinstance(texto_html, str):
        return []
    emails = set()
    DOMINIOS_IGNORAR = [
        "example.com", "dominio.com", "email.com", "teste.com", 
        "correspondentesnaweb.com.br", "wixpress.com", "sentry.io",
        "google.com", "schema.org"
    ]
    for e in re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", texto_html):
        el = e.lower()
        if any(el.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js", ".ico"]):
            continue
        if any(dom in el for dom in DOMINIOS_IGNORAR):
            continue
        emails.add(el)
    return sorted(list(emails))

def extrair_nome(texto_html):
    if not texto_html or not isinstance(texto_html, str):
        return "Não identificado"
    PALAVRAS_IGNORAR = [
        "menu", "login", "cadastr", "pesquisa", "filtro", "buscar", "sobre n", 
        "página inicial", "pagina inicial", "termo", "política", "politica", 
        "contato", "dados para contato", "correspondentes na web", "resultado", 
        "advogado correspondente", "área do", "area do", "esqueci", "home"
    ]
    for m3 in re.finditer(r"<h3[^>]*>([\s\S]*?)</h3>", texto_html, re.I):
        txt = limpar_html(m3.group(1))
        if len(txt) >= 3 and not any(p in txt.lower() for p in PALAVRAS_IGNORAR):
            return txt
    for m1 in re.finditer(r"<h1[^>]*>([\s\S]*?)</h1>", texto_html, re.I):
        txt = limpar_html(m1.group(1))
        if len(txt) >= 3 and not any(p in txt.lower() for p in PALAVRAS_IGNORAR):
            return txt
    for m2 in re.finditer(r"<h2[^>]*>([\s\S]*?)</h2>", texto_html, re.I):
        txt = limpar_html(m2.group(1))
        if len(txt) >= 3 and not any(p in txt.lower() for p in PALAVRAS_IGNORAR):
            return txt
    title_m = re.search(r"<title[^>]*>([\s\S]*?)</title>", texto_html, re.I)
    if title_m:
        t = limpar_html(title_m.group(1))
        for sep in ["|", "-", "–", ":"]:
            if sep in t:
                t = t.split(sep)[0].strip()
        if len(t) >= 3 and not any(p in t.lower() for p in PALAVRAS_IGNORAR):
            return t
    return "Não identificado"

def extrair_oab(texto_html):
    if not texto_html or not isinstance(texto_html, str):
        return "Não informado"
    for m6 in re.finditer(r"<h6[^>]*>([\s\S]*?)</h6>", texto_html, re.I):
        txt = limpar_html(m6.group(1))
        if "oab" in txt.lower():
            return txt
        elif "correspondentes na web" in txt.lower():
            return "Membro (sem OAB informada)"
    reg = re.search(r"OAB(?:\s*[/:\-]?\s*[A-Z]{2})?\s*[:\s.-]?\s*\d{2,6}(?:\.\d{3})?(?:[\-/]\s*[A-Z]{2})?(?:[\-/]?[A-Z])?", texto_html, re.I)
    if reg:
        return html.unescape(reg.group(0).strip())
    return "Não informado"

def extrair_areas_atuacao(texto_html):
    if not texto_html or not isinstance(texto_html, str):
        return []
    areas = []
    m_bloco = re.search(r"(?:<h[45][^>]*>[^<]*?(?:Áreas?\s+de\s+atua[çc][ãa]o|Ramos?\s+de\s+atua[çc][ãa]o)[^<]*?</h[45]>)([\s\S]*?)(?=<h[45]|$)", texto_html, re.I)
    if m_bloco:
        bloco = m_bloco.group(1)
        for m_li in re.finditer(r"<li[^>]*>([\s\S]*?)</li>", bloco, re.I):
            txt = limpar_html(m_li.group(1))
            if txt and 3 <= len(txt) <= 80 and not re.search(r"enviar|mensagem|contato|whatsapp", txt, re.I):
                if txt not in areas:
                    areas.append(txt)
    return areas[:15]

def extrair_endereco(texto_html):
    if not texto_html or not isinstance(texto_html, str):
        return ""
    m_bloco = re.search(r"(?:<h[45][^>]*>[^<]*?(?:Endere[çc]o|Localiza[çc][ãa]o|Onde\s+estou)[^<]*?</h[45]>)([\s\S]*?)(?=<h[45]|<form|$)", texto_html, re.I)
    if m_bloco:
        bloco = m_bloco.group(1)
        m_strong = re.search(r"<strong[^>]*>([\s\S]*?)</strong>", bloco, re.I)
        if m_strong:
            end = limpar_html(m_strong.group(1))
            if end and 2 <= len(end) <= 100:
                return end
        for m_p in re.finditer(r"<p[^>]*>([\s\S]*?)</p>", bloco, re.I):
            txt = limpar_html(m_p.group(1))
            if txt and 2 <= len(txt) <= 100 and not re.search(r"enviar|mensagem|termos", txt, re.I):
                return txt
    m_uf = re.search(r"([A-ZÀ-ÿ][a-zà-ÿ]+(?:[\s-][A-ZÀ-ÿ][a-zà-ÿ]+)*)\s*[-–/]\s*([A-Z]{2})\b", texto_html)
    if m_uf:
        return f"{m_uf.group(1).strip()} - {m_uf.group(2).strip()}"
    return ""

UFS_BRASIL = {
    'AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA',
    'MT', 'MS', 'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN',
    'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO'
}

COORDENADAS_CIDADES = {}
try:
    _caminho_coords = os.path.join(os.path.dirname(os.path.abspath(__file__)), "coordenadas_cidades.json")
    if os.path.exists(_caminho_coords):
        with open(_caminho_coords, "r", encoding="utf-8") as _f_c:
            COORDENADAS_CIDADES = json.load(_f_c)
except Exception:
    COORDENADAS_CIDADES = {}

def normalizar_slug_cidade(nome_ou_slug):
    if not nome_ou_slug:
        return ""
    s = unicodedata.normalize("NFD", str(nome_ou_slug))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")

def formatar_nome_cidade(nome):
    """Padroniza nome da cidade em Title Case preservando partículas comuns (de, da, do, dos, das, d')"""
    if not nome:
        return ""
    partes = str(nome).strip().split()
    resultado = []
    particulas = {"de", "da", "do", "dos", "das", "e"}
    for i, p in enumerate(partes):
        p_lower = p.lower()
        if p_lower.startswith("d'") and len(p_lower) > 2:
            resultado.append("d'" + p_lower[2:].capitalize())
        elif i > 0 and p_lower in particulas:
            resultado.append(p_lower)
        else:
            resultado.append(p.capitalize())
    return " ".join(resultado)

def extrair_cidade_e_uf(texto):
    """Extrai e padroniza o nome da cidade e a UF a partir de um endereço, comarca ou texto livre."""
    if not texto or not isinstance(texto, str):
        return "", ""
    s = str(texto).strip()
    s = re.sub(r"[\r\n\t]+", " ", s)

    # Se for uma URL do correspondentesnaweb: extrai slug da rota
    m_url = re.search(r"/advogado-correspondente/([a-z0-9\-]+)-([a-z]{2})/?", s.lower())
    if m_url:
        return formatar_nome_cidade(m_url.group(1).replace("-", " ")), m_url.group(2).upper()

    # Remove CEP se houver (ex: 06020-000 ou CEP: 06020-000)
    s = re.sub(r"(?:cep\s*[:\s.-]*)?\b\d{5}[-\s]?\d{3}\b", "", s, flags=re.I).strip()

    # 1. Identifica UF de 2 letras
    uf = ""
    m_uf = re.search(r"[-–/,\(\[\s]+([A-Za-z]{2})[\)\]\s]*$", s)
    if m_uf and m_uf.group(1).upper() in UFS_BRASIL:
        uf = m_uf.group(1).upper()
        s_sem_uf = s[:m_uf.start()].strip()
    else:
        m_uf_any = list(re.finditer(r"\b([A-Za-z]{2})\b", s))
        for m in reversed(m_uf_any):
            cand = m.group(1).upper()
            if cand in UFS_BRASIL:
                uf = cand
                s_sem_uf = (s[:m.start()] + " " + s[m.end():]).strip()
                break
        else:
            s_sem_uf = s

    # 2. Extrai cidade a partir do trecho sem UF
    partes = [p.strip() for p in re.split(r"[-–/,\(\)]", s_sem_uf) if p.strip()]
    cidade_candidata = ""
    for p in reversed(partes):
        if re.match(r"^\d+$", p):
            continue
        if len(p) >= 2:
            cidade_candidata = p
            break

    cidade_formatada = formatar_nome_cidade(cidade_candidata)
    return cidade_formatada, uf

def obter_coordenadas_cidade(cidade_str, uf_str=""):
    if not cidade_str or not COORDENADAS_CIDADES:
        return None
    slug_cid = normalizar_slug_cidade(cidade_str)
    uf_clean = uf_str.strip().lower() if uf_str else ""

    # 1. Chave específica com UF: "osasco-sp"
    if uf_clean:
        chave_uf = f"{slug_cid}-{uf_clean}"
        if chave_uf in COORDENADAS_CIDADES:
            return COORDENADAS_CIDADES[chave_uf]

    # 2. Chave direta por slug
    if slug_cid in COORDENADAS_CIDADES:
        return COORDENADAS_CIDADES[slug_cid]

    # 3. Variações ortográficas (d'oeste, santana, etc.)
    variantes = [
        re.sub(r"^sant-ana\b", "santana", slug_cid),
        re.sub(r"-do-oeste$", "-d-oeste", slug_cid),
        re.sub(r"-d-oeste$", "-do-oeste", slug_cid),
        re.sub(r"-d-([a-z]+)$", r"-de-\1", slug_cid),
        re.sub(r"-de-([a-z]+)$", r"-d-\1", slug_cid),
    ]
    for v in variantes:
        if v != slug_cid:
            if uf_clean and f"{v}-{uf_clean}" in COORDENADAS_CIDADES:
                return COORDENADAS_CIDADES[f"{v}-{uf_clean}"]
            if v in COORDENADAS_CIDADES:
                return COORDENADAS_CIDADES[v]

    return None

def calcular_distancia_km_coords(coord1, coord2):
    if not coord1 or not coord2:
        return None
    try:
        lat1, lon1 = float(coord1[0]), float(coord1[1])
        lat2, lon2 = float(coord2[0]), float(coord2[1])
    except (ValueError, TypeError, IndexError):
        return None

    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2.0) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         (math.sin(dlon / 2.0) ** 2))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    dist = R * c
    dist_round = round(dist, 1)
    if dist_round.is_integer():
        return int(dist_round)
    return dist_round

def calcular_dados_localizacao(endereco_texto, cidade_solicitada_param=""):
    """
    Processa localização, cidade do correspondente (origem), cidade solicitada (destino)
    e calcula a distância em km conforme a modelagem estrita solicitada.
    """
    cid_solic, uf_solic = extrair_cidade_e_uf(cidade_solicitada_param)
    cid_corr, uf_corr = extrair_cidade_e_uf(endereco_texto)

    # Se o endereço não informou cidade, adota a cidade solicitada
    if not cid_corr and cid_solic:
        cid_corr = cid_solic
        uf_corr = uf_solic
    elif not cid_solic and cid_corr:
        cid_solic = cid_corr
        uf_solic = uf_corr

    uf_final = uf_corr or uf_solic or ""

    slug_corr = normalizar_slug_cidade(cid_corr)
    slug_solic = normalizar_slug_cidade(cid_solic)

    mesma_cidade = False
    if slug_corr and slug_solic and slug_corr == slug_solic:
        if not uf_corr or not uf_solic or uf_corr == uf_solic:
            mesma_cidade = True

    distancia_km = None
    status_distancia = ""
    rotulo_distancia = ""

    if mesma_cidade:
        distancia_km = 0
        status_distancia = "Mesma cidade"
        rotulo_distancia = "Na própria cidade (0 km)"
    else:
        coord1 = obter_coordenadas_cidade(cid_corr, uf_corr)
        coord2 = obter_coordenadas_cidade(cid_solic, uf_solic)
        dist = calcular_distancia_km_coords(coord1, coord2)
        if dist is not None:
            distancia_km = dist
            if distancia_km == 0:
                mesma_cidade = True
                status_distancia = "Mesma cidade"
                rotulo_distancia = "Na própria cidade (0 km)"
            else:
                status_distancia = f"A {distancia_km} km ({cid_corr})"
                rotulo_distancia = f"{distancia_km} km • {cid_corr}"
        else:
            if cid_corr:
                status_distancia = f"Localizado em {cid_corr}"
                rotulo_distancia = cid_corr

    return {
        "cidade_correspondente": cid_corr,
        "cidade_origem": cid_corr,
        "cidade_solicitada": cid_solic,
        "cidade_destino": cid_solic,
        "uf": uf_final,
        "distancia_km": distancia_km,
        "rotulo_distancia": rotulo_distancia,
        "status_distancia": status_distancia,
        "mesma_cidade": mesma_cidade
    }

def extrair_links_pagina(html_text, target_url, filter_keyword=""):
    if not html_text or not isinstance(html_text, str) or not target_url or not isinstance(target_url, str):
        return []
    parsed = urlparse(target_url)
    is_correspondentes = "correspondentesnaweb.com.br" in (parsed.netloc or "").lower()
    links_achados = []

    link_regex = re.compile(r'<a\b[^>]*?\bhref\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+))', re.I)
    for m in link_regex.finditer(html_text):
        href = (m.group(1) or m.group(2) or m.group(3) or "").strip()
        if not href or href.startswith("#") or href.startswith("javascript:") or href.startswith("mailto:") or href.startswith("tel:"):
            continue

        try:
            full_url = urljoin(target_url, href)
            parsed_full = urlparse(full_url)
        except Exception:
            continue

        if parsed_full.netloc != parsed.netloc:
            continue
        if full_url.rstrip("/") == target_url.rstrip("/"):
            continue

        if filter_keyword:
            if filter_keyword.lower() in full_url.lower() and full_url not in links_achados:
                links_achados.append(full_url)
            continue

        if is_correspondentes:
            if "/advogado-correspondente/" in full_url.lower():
                continue
            if re.search(r"/correspondente/[a-zA-Z0-9\-_]+/?$", full_url.lower()):
                if full_url not in links_achados:
                    links_achados.append(full_url)
            continue

        if any(full_url.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".pdf", ".zip", ".css", ".js", ".svg", ".ico"]):
            continue
        if any(rota in full_url.lower() for rota in ROTAS_IGNORAR):
            continue

        indicios_perfil = ["/perfil/", "/advogado/", "/profissional/", "/doutor/", "/membro/", "/usuario/"]
        if any(ind in full_url.lower() for ind in indicios_perfil):
            if full_url not in links_achados:
                links_achados.append(full_url)
            continue

        parts = [p for p in parsed_full.path.split("/") if p]
        if len(parts) >= 2 and full_url not in links_achados:
            links_achados.append(full_url)

    return links_achados

import csv
import io

def garantir_motor_gmaps():
    """Verifica se o motor do Google Maps Scraper está respondendo na porta GMAPS_PORT.
    Se não estiver e o executável existir, inicia o processo em background."""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{GMAPS_PORT}/api/v1/jobs")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status == 200:
                return True
    except Exception:
        pass

    import shutil
    bin_linux = shutil.which("google-maps-scraper") or shutil.which("google_maps_scraper")
    exe_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "google-maps-scraper-kit", "google_maps_scraper.exe")
    cmd = None
    cwd = None
    if os.path.exists(exe_path):
        cmd = [exe_path, "-web", "-addr", f"127.0.0.1:{GMAPS_PORT}", "-data-folder", "webdata"]
        cwd = os.path.dirname(exe_path)
    elif bin_linux:
        os.makedirs("/tmp/gmapsdata", exist_ok=True)
        cmd = [bin_linux, "-web", "-addr", f"127.0.0.1:{GMAPS_PORT}", "-data-folder", "/tmp/gmapsdata"]
        cwd = "/tmp"

    if cmd:
        try:
            subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(10):
                time.sleep(0.5)
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{GMAPS_PORT}/api/v1/jobs", timeout=1) as resp:
                        if resp.status == 200:
                            return True
                except Exception:
                    pass
            return False
        except Exception as e:
            print(f"[Aviso] Não foi possível iniciar o motor do Google Maps: {e}")
            return False
    return False

def extrair_leads_google_maps(cidade_solic, uf_solic="", lat=None, lon=None, depth=2, extrair_emails=True, termo_personalizado=""):
    """
    Executa busca no Google Maps através do motor local (gosom/google-maps-scraper)
    e padroniza os resultados no schema unificado de contatos do Disque Diligentes.
    """
    garantir_motor_gmaps()

    engine_url = f"http://127.0.0.1:{GMAPS_PORT}/api/v1/jobs"
    if termo_personalizado and termo_personalizado.strip():
        kw = termo_personalizado.strip()
    elif uf_solic:
        kw = f"advogados em {cidade_solic} {uf_solic}".strip()
    else:
        kw = f"advogados em {cidade_solic}".strip()

    if lat is None or lon is None:
        coords = obter_coordenadas_cidade(cidade_solic, uf_solic)
        if coords:
            lat = coords[0]
            lon = coords[1]

    lat_str = str(lat) if lat is not None else "-23.5505"
    lon_str = str(lon) if lon is not None else "-46.6333"

    payload = {
        "name": f"gmaps_{normalizar_slug_cidade(cidade_solic)}",
        "keywords": [kw],
        "lang": "pt",
        "zoom": 15,
        "lat": lat_str,
        "lon": lon_str,
        "fast_mode": True,
        "radius": 10000,
        "depth": max(1, min(depth, 5)),
        "email": bool(extrair_emails),
        "max_time": 90
    }

    req = urllib.request.Request(
        engine_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=10) as resp:
        job = json.loads(resp.read().decode("utf-8"))
        job_id = job.get("id") or job.get("ID")

    if not job_id:
        return []

    status_url = f"{engine_url}/{job_id}"
    for _ in range(45):
        time.sleep(1)
        with urllib.request.urlopen(status_url, timeout=10) as resp:
            st = json.loads(resp.read().decode("utf-8"))
            if st.get("Status") in ["ok", "failed"]:
                break

    download_url = f"{status_url}/download"
    with urllib.request.urlopen(download_url, timeout=15) as resp:
        csv_text = resp.read().decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)

    padronizados = []
    for r in rows:
        nome = (r.get("title") or "").strip()
        if not nome:
            continue

        raw_phone = (r.get("phone") or "").strip()
        tel_limpo = re.sub(r"\D", "", raw_phone)
        if tel_limpo.startswith("0"):
            tel_limpo = tel_limpo[1:]
        if len(tel_limpo) in [10, 11]:
            tel_limpo = "55" + tel_limpo
        eh_whats = len(tel_limpo) == 13 and tel_limpo[4] == "9"
        tels = []
        if tel_limpo:
            tels.append(TelefoneItem(
                numero_formatado=raw_phone,
                numero_limpo=tel_limpo,
                tipo="celular" if eh_whats else "fixo",
                eh_whatsapp=eh_whats
            ))

        raw_emails = (r.get("emails") or "").strip()
        emails = [e.strip() for e in re.split(r"[,; ]+", raw_emails) if "@" in e]

        item = {
            "nome": nome,
            "cidade_correspondente": cidade_solic,
            "cidade_origem": cidade_solic,
            "cidade_solicitada": cidade_solic,
            "cidade_destino": cidade_solic,
            "uf": uf_solic,
            "distancia_km": 0,
            "rotulo_distancia": "Na própria cidade (0 km)",
            "status_distancia": "Mesma cidade",
            "mesma_cidade": True,
            "oab": "Google Maps",
            "telefones": tels,
            "telefone_principal": tel_limpo,
            "emails": emails,
            "areas_atuacao": [(r.get("category") or "Advocacia / Escritório").strip()],
            "endereco": (r.get("address") or "").strip(),
            "comarca": f"{cidade_solic} - {uf_solic}" if uf_solic else cidade_solic,
            "_distanciaKm": 0,
            "url": (r.get("link") or r.get("website") or "").strip(),
            "fonte": "Google Maps"
        }
        padronizados.append(item)

    return padronizados

import time

RATE_LIMIT_MAP = {}
RATE_LIMIT_LOCK = threading.Lock()
RATE_LIMIT_WINDOW_S = 60.0
RATE_LIMIT_MAX_REQ = 240
MAX_PAYLOAD_BYTES = 16384
GMAPS_SEMAPHORE = threading.Semaphore(1)

def verificar_rate_limit(ip):
    agora = time.time()
    chave = ip or "anon"
    with RATE_LIMIT_LOCK:
        if len(RATE_LIMIT_MAP) > 1000:
            expirados = [k for k, v in list(RATE_LIMIT_MAP.items()) if agora - v["inicio"] > RATE_LIMIT_WINDOW_S]
            for k in expirados:
                RATE_LIMIT_MAP.pop(k, None)
        reg = RATE_LIMIT_MAP.get(chave)
        if not reg or (agora - reg["inicio"]) > RATE_LIMIT_WINDOW_S:
            RATE_LIMIT_MAP[chave] = {"inicio": agora, "cont": 1}
            return True
        reg["cont"] += 1
        return reg["cont"] <= RATE_LIMIT_MAX_REQ

def validar_content_type_html(content_type):
    if not content_type or not isinstance(content_type, str):
        return True
    ct = content_type.lower().split(";")[0].strip()
    if not ct:
        return True
    return ct in ("text/html", "application/xhtml+xml", "text/plain", "application/xml", "text/xml")

class CustomHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        super().__init__(*args, directory=base_dir, **kwargs)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data: https:; frame-src https://maps.google.com https://www.google.com; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        super().end_headers()

    def _validar_origem_cors(self):
        origin = (self.headers.get("Origin") or "").strip()
        req_host = (self.headers.get("Host") or "").split(":")[0].lower()
        if not origin:
            if req_host in ("localhost", "127.0.0.1"):
                return True, f"http://{req_host}"
            return True, f"https://{req_host}" if req_host else "null"
        try:
            u = urlparse(origin)
            host = (u.hostname or "").lower()
            if host in ("localhost", "127.0.0.1") or (req_host and host == req_host) or host.endswith(".netlify.app") or host.endswith(".onrender.com"):
                return True, origin
            return False, "null"
        except Exception:
            return False, "null"

    def _enviar_json(self, status_code, payload, origin_header="null"):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", origin_header)
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-App-Key")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Vary", "Origin")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        rota_limpa = urlparse(self.path).path.lower()
        arquivos_bloqueados = (
            "/server_local.py", "/iniciar_local.bat", "/package.json",
            "/netlify.toml", "/_redirects", "/.gitignore",
            "/dockerfile", "/entrypoint.sh", "/render.yaml"
        )
        if (
            rota_limpa in arquivos_bloqueados or
            rota_limpa.startswith("/netlify/") or
            rota_limpa.startswith("/google-maps-scraper-kit/") or
            rota_limpa.endswith((".md", ".py", ".bat", ".sh", ".exe", ".yaml", ".yml"))
        ):
            self.send_error(404, "Not Found")
            return
        return super().do_GET()

    def do_OPTIONS(self):
        permitido, origin_hdr = self._validar_origem_cors()
        if not permitido:
            self._enviar_json(403, {"erro": "Origem não autorizada pela política de CORS."}, origin_hdr)
            return
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", origin_hdr)
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-App-Key")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Vary", "Origin")
        self.end_headers()

    def do_POST(self):
        rota_limpa = urlparse(self.path).path
        if rota_limpa in ["/api/extrair", "/.netlify/functions/extrair"]:
            permitido, origin_hdr = self._validar_origem_cors()
            if not permitido:
                self._enviar_json(403, {"erro": "Origem não autorizada pela política de CORS."}, origin_hdr)
                return

            if APP_ACCESS_TOKEN:
                token_req = (self.headers.get("X-App-Key") or "").strip()
                if token_req != APP_ACCESS_TOKEN:
                    self._enviar_json(401, {"erro": "Acesso não autorizado. Chave de acesso inválida ou ausente."}, origin_hdr)
                    return

            client_ip = self.client_address[0] if self.client_address else "local"
            if not verificar_rate_limit(client_ip):
                self._enviar_json(429, {"erro": "Limite de requisições por minuto excedido. Aguarde alguns segundos."}, origin_hdr)
                return

            try:
                content_length = int(self.headers.get("Content-Length", 0))
            except (ValueError, TypeError):
                self._enviar_json(400, {"erro": "Cabeçalho Content-Length inválido."}, origin_hdr)
                return

            if content_length < 0:
                self._enviar_json(400, {"erro": "Tamanho de requisição inválido."}, origin_hdr)
                return
            if content_length > MAX_PAYLOAD_BYTES:
                self._enviar_json(413, {"erro": "Payload excede o tamanho máximo permitido (16 KB)."}, origin_hdr)
                return

            try:
                post_data = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else ""
                params = json.loads(post_data) if post_data else {}
                if not isinstance(params, dict):
                    self._enviar_json(400, {"erro": "Formato de payload inválido: esperado objeto JSON."}, origin_hdr)
                    return
            except Exception:
                self._enviar_json(400, {"erro": "JSON inválido no corpo da requisição."}, origin_hdr)
                return

            acao = str(params.get("acao", "perfil") or "perfil").strip().lower()
            if acao not in ("listar", "perfil", "gmaps"):
                self._enviar_json(400, {"erro": "Ação inválida. Valores aceitos: 'listar', 'perfil' ou 'gmaps'."}, origin_hdr)
                return

            if acao == "gmaps":
                cidade = str(params.get("cidade", "") or "").strip()[:100]
                uf = str(params.get("uf", "") or "").strip().upper()[:2]
                palavra_chave = str(params.get("termo", "") or params.get("keyword", "") or "").strip()[:100]
                try:
                    depth = int(params.get("depth", 2) or 2)
                except (ValueError, TypeError):
                    depth = 2
                depth = max(1, min(depth, 5))
                extrair_emails_flag = bool(params.get("email", True))

                if not cidade:
                    self._enviar_json(400, {"erro": "Parâmetro 'cidade' é obrigatório para busca no Google Maps."}, origin_hdr)
                    return

                adquiriu = GMAPS_SEMAPHORE.acquire(blocking=False)
                if not adquiriu:
                    self._enviar_json(429, {"erro": "Já existe uma varredura do Google Maps em andamento. Aguarde a conclusão e tente novamente."}, origin_hdr)
                    return

                coords = obter_coordenadas_cidade(cidade, uf)
                lat = coords[0] if coords else None
                lon = coords[1] if coords else None

                try:
                    contatos = extrair_leads_google_maps(
                        cidade_solic=cidade,
                        uf_solic=uf,
                        lat=lat,
                        lon=lon,
                        depth=depth,
                        extrair_emails=extrair_emails_flag,
                        termo_personalizado=palavra_chave
                    )
                    self._enviar_json(200, {"dados": contatos, "total": len(contatos), "fonte": "Google Maps"}, origin_hdr)
                    return
                except urllib.error.URLError:
                    self._enviar_json(503, {"erro": f"Motor Google Maps Scraper offline na porta {GMAPS_PORT}. Inicie o scraper localmente."}, origin_hdr)
                    return
                except Exception as e_gmaps:
                    sys.stderr.write(f"[ERRO GMAPS] {repr(e_gmaps)}\n")
                    self._enviar_json(500, {"erro": "Falha interna ao processar a extração no Google Maps. Tente novamente."}, origin_hdr)
                    return
                finally:
                    GMAPS_SEMAPHORE.release()

            target_url = str(params.get("url", "") or "").strip()
            if target_url and not target_url.startswith("http://") and not target_url.startswith("https://"):
                target_url = "https://" + target_url

            filter_keyword = str(params.get("filter_keyword", "") or "").strip()[:120]
            try:
                max_links = int(params.get("max_links", 0)) if params.get("max_links") is not None else 0
                max_links = min(max(max_links, 0), 500)
            except (ValueError, TypeError):
                max_links = 0

            if not target_url or not validar_url_segura(target_url, resolver_dns=True):
                self._enviar_json(400, {"erro": "URL inválida ou não autorizada para consulta pública."}, origin_hdr)
                return

            try:
                req = urllib.request.Request(target_url, headers=HEADERS)
                with SAFE_OPENER.open(req, timeout=8) as resp:
                    final_url = resp.geturl()
                    if final_url and not validar_url_segura(final_url, resolver_dns=True):
                        self._enviar_json(400, {"erro": "Redirecionamento para endereço não autorizado bloqueado."}, origin_hdr)
                        return
                    resp_ct = resp.headers.get("Content-Type", "") if hasattr(resp, "headers") else ""
                    if not validar_content_type_html(resp_ct):
                        self._enviar_json(415, {"erro": "Tipo de conteúdo não suportado. Apenas páginas HTML/texto são permitidas."}, origin_hdr)
                        return
                    raw_bytes = resp.read(5 * 1024 * 1024)
                    try:
                        html_content = raw_bytes.decode("utf-8")
                        if "\ufffd" in html_content:
                            html_content = raw_bytes.decode("latin1", errors="replace")
                    except Exception:
                        html_content = raw_bytes.decode("latin1", errors="replace")

                if acao == "listar":
                    links = extrair_links_pagina(html_content, target_url, filter_keyword)

                    # O site correspondentesnaweb.com.br limita cada página a 20 perfis com rotação aleatória (ORDER BY RAND()).
                    # Para regiões com mais de 20 correspondentes, acumulamos as passadas rotativas até esgotar todos os cadastrados.
                    is_corresp = "correspondentesnaweb.com.br/advogado-correspondente/" in target_url.lower()
                    if is_corresp and len(links) >= 20:
                        vistos = set(links)
                        max_passes = 10
                        passes_sem_novos = 0
                        for p in range(2, max_passes + 1):
                            try:
                                p_req = urllib.request.Request(target_url, headers=HEADERS)
                                with SAFE_OPENER.open(p_req, timeout=4) as p_resp:
                                    p_final_url = p_resp.geturl()
                                    if p_final_url and not validar_url_segura(p_final_url, resolver_dns=True):
                                        break
                                    p_ct = p_resp.headers.get("Content-Type", "") if hasattr(p_resp, "headers") else ""
                                    if not validar_content_type_html(p_ct):
                                        break
                                    p_bytes = p_resp.read(5 * 1024 * 1024)
                                    try:
                                        p_html = p_bytes.decode("utf-8")
                                        if "\ufffd" in p_html:
                                            p_html = p_bytes.decode("latin1", errors="replace")
                                    except Exception:
                                        p_html = p_bytes.decode("latin1", errors="replace")
                                    p_links = extrair_links_pagina(p_html, target_url, filter_keyword)
                                    novos = 0
                                    for l in p_links:
                                        if l not in vistos:
                                            vistos.add(l)
                                            links.append(l)
                                            novos += 1
                                    if novos == 0:
                                        passes_sem_novos += 1
                                        if passes_sem_novos >= 2:
                                            break
                                    else:
                                        passes_sem_novos = 0
                            except Exception:
                                pass

                    links_finais = links[:max_links] if max_links > 0 else links
                    self._enviar_json(200, {"links": links_finais}, origin_hdr)
                    return

                # acao == "perfil"
                nome = extrair_nome(html_content)
                oab = extrair_oab(html_content)
                telefones = validar_telefones(html_content)
                emails = extrair_emails(html_content)
                areas_atuacao = extrair_areas_atuacao(html_content)
                endereco = extrair_endereco(html_content)

                cidade_solicitada_param = (
                    params.get("cidade_solicitada") or
                    params.get("cidade_destino") or
                    params.get("comarca") or
                    ""
                )

                loc_dados = calcular_dados_localizacao(endereco, cidade_solicitada_param)

                # Comarca legada para retrocompatibilidade total
                comarca_retro = (
                    f"{loc_dados['cidade_solicitada']} - {loc_dados['uf']}"
                    if loc_dados["cidade_solicitada"] and loc_dados["uf"]
                    else (loc_dados["cidade_solicitada"] or cidade_solicitada_param or "Não informada")
                )

                telefone_principal = telefones[0]["numero_limpo"] if telefones else ""

                dados = {
                    "nome": nome,
                    "cidade_correspondente": loc_dados["cidade_correspondente"],
                    "cidade_origem": loc_dados["cidade_origem"],
                    "cidade_solicitada": loc_dados["cidade_solicitada"],
                    "cidade_destino": loc_dados["cidade_destino"],
                    "uf": loc_dados["uf"],
                    "distancia_km": loc_dados["distancia_km"],
                    "rotulo_distancia": loc_dados["rotulo_distancia"],
                    "status_distancia": loc_dados["status_distancia"],
                    "mesma_cidade": loc_dados["mesma_cidade"],
                    "oab": oab,
                    "telefones": telefones,
                    "telefone_principal": telefone_principal,
                    "emails": emails,
                    "areas_atuacao": areas_atuacao,
                    "endereco": endereco,
                    "comarca": comarca_retro,
                    "_distanciaKm": loc_dados["distancia_km"],
                    "url": target_url
                }

                self._enviar_json(200, {"dados": dados}, origin_hdr)
                return

            except urllib.error.HTTPError as e_http:
                self._enviar_json(e_http.code, {"erro": f"Página retornou status HTTP {e_http.code}."}, origin_hdr)
                return
            except Exception:
                self._enviar_json(502, {"erro": "Não foi possível estabelecer conexão com a página solicitada."}, origin_hdr)
                return

        self.send_error(404, "Rota não encontrada.")

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    print("\n" + "="*60)
    print("Servidor Local do Extrator Netlify iniciado!")
    print(f"Acesse no navegador: http://localhost:{PORT}")
    print("="*60 + "\n")
    httpd = ThreadingHTTPServer((HOST, PORT), CustomHandler)
    httpd.serve_forever()


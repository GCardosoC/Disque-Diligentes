# 🚀 Disque Diligentes - Guia de Deploy no Render (100% Gratuito)

Esta pasta foi especialmente preparada para você subir no **Render.com** de forma rápida, limpa e sem complicação, para que sua namorada possa acessar a plataforma direto do navegador em qualquer celular, tablet ou computador.

---

## 📦 Arquivos Prontos nesta Pasta
- `Dockerfile`: Configura o ambiente Linux com o motor do Google Maps Scraper (Chromium) + Python 3.
- `entrypoint.sh`: Inicializa em background o motor do Maps (porta 8080) e o servidor público do app (porta 10000).
- `render.yaml`: Blueprint automático para o Render reconhecer o serviço como Web Service Docker.
- `server_local.py`: Backend em Python com todas as 6 camadas de segurança e endpoints de extração.
- `index.html`: Interface completa e responsiva do Disque Diligentes.
- `cidades_brasil.json` & `coordenadas_cidades.json`: Base nacional de comarcas e geolocalização.
- `.dockerignore`, `.gitignore` e `.gitattributes`: Garantem upload leve (< 1 MB) e quebras de linha compatíveis com Linux (LF).

---

## 🛠️ Passo a Passo para Subir no Render

### Passo 1: Criar um Repositório no GitHub
1. Acesse [github.com/new](https://github.com/new) e crie um repositório (pode ser **Privado** ou **Público**), por exemplo: `disque-diligentes`.
2. No seu terminal, dentro desta pasta `render_deploy`, execute:
```bash
git init
git add .
git commit -m "Deploy Disque Diligentes no Render"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/disque-diligentes.git
git push -u origin main
```
*(Ou arraste todos os arquivos desta pasta diretamente pela interface web do GitHub em "Upload files")*.

---

### Passo 2: Conectar e Publicar no Render
1. Acesse [dashboard.render.com](https://dashboard.render.com/) e faça login (pode entrar com sua conta do GitHub).
2. Clique no botão azul **"New +"** no topo direito e selecione **"Web Service"**.
3. Escolha **"Build and deploy from a Git repository"** e selecione o repositório `disque-diligentes` que você acabou de criar.
4. Preencha as configurações básicas:
   - **Name:** `disque-diligentes` (ou o nome que preferir).
   - **Region:** `Ohio (US East)` ou `Oregon (US West)`.
   - **Language / Environment:** `Docker` *(o Render detecta automaticamente pelo Dockerfile)*.
   - **Instance Type:** `Free` (0.5 CPU, 512 MB RAM - gratuito).
5. Clique em **"Deploy Web Service"** no final da página!

---

### Passo 3: Pronto! 🎉
- O Render vai baixar a imagem Docker, preparar o Chromium e ligar o servidor. O processo leva cerca de 2 a 3 minutos.
- Assim que o status mudar para **"Live"**, o Render vai gerar um link público como:
  👉 `https://disque-diligentes-xxxx.onrender.com`
- Envie esse link para a sua namorada! Ela poderá pesquisar correspondentes na web ou no Google Maps e disparar mensagens para o WhatsApp com 1 clique!

---

### 🔒 Dica Extra: Proteger com Senha / Chave (Opcional)
Se você quiser que somente ela tenha acesso:
1. No painel do seu serviço no Render, vá na aba **"Environment"**.
2. Adicione a variável:
   - **Key:** `APP_ACCESS_TOKEN`
   - **Value:** `UmaSenhaForteCriadaPorVoce`
3. Salve as alterações.
4. Ao abrir o site, basta informar a chave no cabeçalho ou configurar o acesso exclusivo!

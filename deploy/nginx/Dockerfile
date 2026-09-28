# Housetel web — production image: the compiled SPA served by nginx, which also proxies /api to gunicorn,
# serves /static and the public photos of /media, and never the private files (they are not in its volumes).
# Build context: ./frontend (see docker-compose.prod.yml). The nginx configuration is mounted from deploy/nginx/.

# ---- 1. Build the SPA -----------------------------------------------------------------------------------------
FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# Type checking and lint run in CI (.github/workflows/ci.yml); the image only bundles.
RUN npx vite build --outDir /app/dist --emptyOutDir
# The inline <script> of index.html (theme and language before the first paint) is allowed by the CSP through
# its sha256 hash, computed from the built file so it always matches.
RUN node -e "\
const fs = require('node:fs'); const crypto = require('node:crypto');\
const html = fs.readFileSync('/app/dist/index.html', 'utf8');\
const hashes = [...html.matchAll(/<script(?![^>]*\\bsrc=)[^>]*>([\\s\\S]*?)<\\/script>/g)]\
  .map((m) => m[1]).filter((code) => code.trim())\
  .map((code) => \"'sha256-\" + crypto.createHash('sha256').update(code, 'utf8').digest('base64') + \"'\");\
fs.writeFileSync('/app/csp-script-hashes.txt', hashes.join(' '));\
console.log('CSP inline script hashes:', hashes.join(' ') || '(none)');"

# ---- 2. Serve it --------------------------------------------------------------------------------------------
FROM nginx:1.29-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY --from=build /app/csp-script-hashes.txt /etc/nginx/csp-script-hashes.txt
# Exposes the hashes to the template renderer of the official image (20-envsubst-on-templates.sh runs after it).
RUN printf '%s\n' '#!/bin/sh' \
      'CSP_SCRIPT_HASHES="$(cat /etc/nginx/csp-script-hashes.txt 2>/dev/null)"' \
      'export CSP_SCRIPT_HASHES' > /docker-entrypoint.d/05-housetel-csp.envsh \
    && chmod +x /docker-entrypoint.d/05-housetel-csp.envsh \
    && rm -f /etc/nginx/conf.d/default.conf
EXPOSE 8080

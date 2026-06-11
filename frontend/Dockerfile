# Phase 5.4 — Frontend image. Multi-stage: build the static bundle with Node,
# then serve it with a tiny nginx that also reverse-proxies /api to the backend.

# ---- Stage 1: build ----
# node:22 (not your laptop's 20) only needs to satisfy Vite 8's build; it never
# ships to production. Alpine keeps the build image small.
FROM node:22-alpine AS build
WORKDIR /app

# Copy manifests first so this layer (the slow install) is cached and only
# re-runs when dependencies change, not on every source edit.
COPY package*.json ./
# We use `npm install`, not `npm ci`, ON PURPOSE. The lockfile is generated on
# Windows, which omits Linux-only optional native deps (e.g. @emnapi/*). `npm ci`
# is strict and refuses when the lockfile is missing those Linux packages, so it
# fails inside this Alpine image. `npm install` resolves against package.json and
# pulls the platform-correct packages here. Trade-off: we give up npm ci's
# byte-for-byte reproducibility — acceptable for a homelab project; a strict
# pipeline would instead pin the offending dep or generate the lockfile on Linux.
RUN npm install --no-audit --no-fund

# Now the source, then build. `npm run build` (vite build) emits /app/dist:
# plain static HTML/CSS/JS, with the /api relative paths from App.jsx baked in.
COPY . .
RUN npm run build

# ---- Stage 2: serve ----
# Everything from stage 1 (Node, node_modules, Vite) is discarded here. We keep
# only the built static files plus nginx — a small, production-style image.
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
# nginx:alpine's built-in CMD already runs nginx in the foreground as PID 1.

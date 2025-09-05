FROM node:20-slim

# Базовый минимум
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev || npm install --omit=dev
COPY . .

ENV NODE_ENV=production

# HEALTHCHECK по динамическому порту Railway
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD node -e "const p=process.env.PORT||3000; fetch('http://127.0.0.1:'+p+'/version').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node","index.js"]

FROM node:20-slim
ENV NODE_ENV=production
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/*
COPY package*.json ./
RUN set -eux; if [ -f package-lock.json ]; then npm ci --omit=dev; else npm install --omit=dev; fi
COPY . .
RUN chown -R node:node /app
USER node
ENV PORT=3000
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 CMD node -e "require('http').get({host: '127.0.0.1', port: process.env.PORT || 3000, path: '/version'}, res => { process.exit(res.statusCode === 200 ? 0 : 1); }).on('error', () => process.exit(1))"
CMD ["node", "index.js"]

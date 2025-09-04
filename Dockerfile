FROM node:20-slim
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --omit=dev || npm i --omit=dev
COPY index.js .
ENV NODE_ENV=production
ENV PORT=8080
EXPOSE 8080
CMD ["node","index.js"]

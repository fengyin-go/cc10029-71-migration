# 构建前端产物
FROM node:20-alpine AS build
WORKDIR /srv/web
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

# 运行：同端口同时提供 / 与 /portal/ 两套入口
FROM node:20-alpine
WORKDIR /srv/web
COPY --from=build /srv/web/dist ./dist
COPY server.mjs ./
ENV PORT=5173 HOST=0.0.0.0
EXPOSE 5173
CMD ["node", "server.mjs"]

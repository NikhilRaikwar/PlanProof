FROM node:22-bookworm-slim AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci
COPY . ./

# This public URL is intentionally the only build-time configuration value.
ARG NEXT_PUBLIC_PLANPROOF_API_URL
ENV NEXT_PUBLIC_PLANPROOF_API_URL=$NEXT_PUBLIC_PLANPROOF_API_URL
RUN npm run build

FROM node:22-bookworm-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=8080

COPY --from=build /app/public ./public
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static

USER node
EXPOSE 8080
CMD ["node", "server.js"]

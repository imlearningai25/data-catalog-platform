FROM node:20-slim AS builder

WORKDIR /app

ARG VITE_API_GATEWAY_URL=http://localhost:8000
ENV VITE_API_GATEWAY_URL=$VITE_API_GATEWAY_URL

COPY package.json .
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

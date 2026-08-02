ARG FRONTEND_BASE_IMAGE=velpos-frontend-base:local
FROM ${FRONTEND_BASE_IMAGE} AS build

WORKDIR /app
COPY . .
RUN npm run build

# Stage 2: Serve
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

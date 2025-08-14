FROM node:18-alpine AS build
WORKDIR /src
COPY app/frontend/package.json ./
COPY app/frontend/package-lock.json ./
RUN npm ci
COPY app/frontend ./
# Set API base at build time if needed:
#   docker build --build-arg REACT_APP_API_BASE=http://backend:8000 ...
ARG REACT_APP_API_BASE=""
ENV REACT_APP_API_BASE=$REACT_APP_API_BASE
RUN npm run build

FROM nginx:alpine
COPY --from=build /src/build /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

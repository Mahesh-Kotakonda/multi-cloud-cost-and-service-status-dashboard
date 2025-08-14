FROM node:18-alpine AS build
WORKDIR /src
COPY app/frontend/package*.json ./
RUN npm install
COPY app/frontend ./
ARG REACT_APP_API_BASE=""
ENV REACT_APP_API_BASE=$REACT_APP_API_BASE
RUN npm run build

FROM nginx:alpine
COPY --from=build /src/build /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

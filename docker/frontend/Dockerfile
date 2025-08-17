# Stage 1: Build React app
FROM node:20-alpine AS build

WORKDIR /app/frontend

COPY package.json package-lock.json* ./
RUN npm install

COPY . ./
RUN npm run build

# Stage 2: Serve with Node
FROM node:20-alpine

WORKDIR /app/frontend

# Copy only the build and server file
COPY --from=build /app/frontend/build ./build
COPY --from=build /app/frontend/package.json ./package.json
COPY server.js ./server.js

# Install express
RUN npm install express

EXPOSE 80

CMD ["node", "server.js"]

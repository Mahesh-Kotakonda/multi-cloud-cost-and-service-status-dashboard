# Stage 1: Build React app
FROM node:20-alpine AS build

# Workdir
WORKDIR /app/frontend

# Copy package.json and package-lock.json first for caching
COPY ../../app/frontend/package.json ../../app/frontend/package-lock.json* ./

# Install dependencies
RUN npm install

# Copy all frontend source code
COPY ../../app/frontend/. ./

# Build the app
RUN npm run build

# Stage 2: Serve with Nginx
FROM nginx:alpine

# Copy built app to Nginx html directory
COPY --from=build /app/frontend/build /usr/share/nginx/html

# Expose port 80
EXPOSE 80

# Start Nginx
CMD ["nginx", "-g", "daemon off;"]

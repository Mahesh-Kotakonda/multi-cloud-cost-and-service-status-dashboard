FROM node:20-alpine

WORKDIR /app/frontend

# Copy package.json and install dependencies
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

# Copy all frontend source
COPY frontend/. ./

EXPOSE 3000

CMD ["npm", "start"]

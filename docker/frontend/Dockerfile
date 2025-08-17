FROM node:20-alpine

WORKDIR /app/frontend

# Copy package.json and install dependencies
COPY app/frontend/package.json app/frontend/package-lock.json* ./
RUN npm install

# Copy all frontend source
COPY app/frontend/. ./

EXPOSE 3000
CMD ["npm", "start"]

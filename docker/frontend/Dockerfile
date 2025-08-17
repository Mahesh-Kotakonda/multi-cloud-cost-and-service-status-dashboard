# Build React app
FROM node:20-alpine

# Set working directory
WORKDIR /app/frontend

# Copy package.json and install dependencies
COPY package.json package-lock.json* ./
RUN npm install

# Copy source code
COPY . .

# Expose port React uses by default
EXPOSE 3000

# Start the app
CMD ["npm", "start"]

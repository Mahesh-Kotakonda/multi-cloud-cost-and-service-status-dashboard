# Use Node.js Alpine image
FROM node:20-alpine

# Set working directory
WORKDIR /app/frontend

# Copy package.json and package-lock.json first
COPY app/frontend/package.json app/frontend/package-lock.json* ./

# Install dependencies
RUN npm install

# Copy all source files
COPY app/frontend/. ./

# Expose port 3000 for React dev server
EXPOSE 3000

# Start React dev server on all interfaces
CMD ["npm", "start", "--", "--host", "0.0.0.0"]

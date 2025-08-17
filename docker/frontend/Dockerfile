# Use Node base image
FROM node:20-alpine

# Set working directory
WORKDIR /app/frontend

# Copy package files and install dependencies
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

# Copy all frontend code
COPY frontend/. ./

# Build the React app
RUN npm run build

# Install serve to run the build folder
RUN npm install -g serve

# Expose port
EXPOSE 80

# Launch the app
CMD ["serve", "-s", "build", "-l", "80"]

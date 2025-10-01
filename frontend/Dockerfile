# Use a Node.js base image
FROM node:lts-alpine

# Set the working directory inside the container
WORKDIR /front

# Copy package.json and package-lock.json (if present)
# to install dependencies efficiently
COPY package*.json ./

# Install project dependencies
RUN npm install

# Copy the rest of your application code
COPY . .

# Expose the port your development server runs on (e.g., 3000 for React, 8080 for Vue)
EXPOSE 3000

# Define the command to run when the container starts
CMD ["npm", "run", "dev"]
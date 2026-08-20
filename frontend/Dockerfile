# Development image. docker-compose.yml mounts ./frontend over /app for HMR, so
# this runs vite's dev server rather than building static assets — production
# deploys go to Vercel straight from the repo, not from this image.
#
# docker-compose.yml referenced this file before it existed, so
# `docker-compose up --build` failed outright with "Dockerfile not found".
FROM node:20-alpine

WORKDIR /app

# Manifest + lockfile only, so this layer is cached and `npm ci` does not re-run on
# every source edit. `ci` rather than `install`: it installs exactly what the
# lockfile pins and fails if the two have drifted, instead of quietly resolving
# something newer than the host ever tested.
COPY package.json package-lock.json ./
RUN npm ci

# .dockerignore excludes the host's node_modules — those are host-platform binaries
# and copying them over the layer above would break esbuild's native binding.
COPY . .

EXPOSE 3000

# --host binds 0.0.0.0 so the published port actually answers; vite defaults to
# localhost, which inside a container is only reachable from the container itself.
# vite.config.js already sets host and port, and these repeat it so the container
# stays correct if that config changes.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]

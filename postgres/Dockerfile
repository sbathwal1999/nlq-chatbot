# Use the official lightweight PostgreSQL image.
# Alpine variant keeps the image small.
FROM postgres:16-alpine

# init.sql is copied into the entrypoint init directory.
# PostgreSQL runs all *.sql files here automatically on first startup.
COPY init.sql /docker-entrypoint-initdb.d/init.sql

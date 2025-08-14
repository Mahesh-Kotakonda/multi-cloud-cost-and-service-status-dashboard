FROM postgres:15-alpine
ENV POSTGRES_DB=metricsdb \
    POSTGRES_USER=postgres \
    POSTGRES_PASSWORD=postgres
COPY app/database/schema.sql /docker-entrypoint-initdb.d/
EXPOSE 5432

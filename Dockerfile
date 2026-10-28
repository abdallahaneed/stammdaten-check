FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY stammdaten_check ./stammdaten_check
COPY sql ./sql
COPY reference ./reference
COPY config ./config
# editable, so sql/, reference/ and config/ stay next to the code
RUN pip install --no-cache-dir -e .

# runs and the database live here, mount a volume to keep them
ENV STAMMDATEN_HOME=/data
VOLUME /data
EXPOSE 8000

RUN useradd --create-home app && mkdir -p /data && chown app /data
USER app
CMD ["stammdaten-check", "serve", "--host", "0.0.0.0", "--port", "8000", "--home", "/data"]

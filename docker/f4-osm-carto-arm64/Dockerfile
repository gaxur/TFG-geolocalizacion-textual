FROM ubuntu@sha256:08571ca13e00ca07a2a84eab83a959b4242e22cceb16486a11bef1428c9e93a7

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install --no-install-recommends -y \
    ca-certificates curl gdal-bin git mapnik-utils nodejs npm osm2pgsql \
    osmium-tool postgresql-16 postgresql-16-postgis-3 postgresql-client-16 \
    patch python3-mapnik python3-pil python3-psycopg2 python3-requests python3-yaml \
    fonts-hanazono fonts-noto-cjk fonts-noto-core fonts-noto-extra \
    fonts-noto-mono fonts-noto-ui-core fonts-noto-ui-extra fonts-noto-unhinted unzip \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global carto@1.2.0 \
    && npm cache clean --force

WORKDIR /workspace/project

ENV PGDATABASE=gis \
    PGUSER=root \
    PYTHONPATH=/workspace/project

CMD ["bash"]

FROM alpine:3.15 AS builder
RUN apk add --no-cache build-base pkgconf libshout-dev libxml2-dev check-dev taglib-dev bsd-compat-headers \
 && cd /tmp \
 && wget https://ftp.osuosl.org/pub/xiph/releases/ezstream/ezstream-0.6.1.tar.gz \
 && tar xfz ezstream-0.6.1.tar.gz \
 && cd ezstream-0.6.1 \
 && ./configure \
 && make all install

FROM alpine:3.15
MAINTAINER hex@umonkey.net
COPY --from=builder /usr/local/bin/ezstream /usr/bin/ezstream
RUN apk add --no-cache python3 py3-pip py3-wheel supervisor flac mpg123 lame sox vorbis-tools icecast libshout taglib
COPY requirements.txt /app/
RUN pip3 install -r /app/requirements.txt \
 && rm -f requirements.txt \
 && rm -rf /root/.cache
COPY bin /app/bin
COPY src /app/src
COPY data /app/data.dist
COPY website /app/website
COPY patches /app/patches
COPY build/rootfs/ /

WORKDIR /app
ENV ARDJ_CONFIG_DIR=/app/data
ENV PYTHONPATH=/app/src

EXPOSE 8000/tcp

CMD ["/startup.sh"]

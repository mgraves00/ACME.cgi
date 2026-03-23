#
FROM docker.io/library/alpine:latest@sha256:25109184c71bdad752c8312a8623239686a9a2071e8825f20acb8f2198c3f659 AS builder

RUN apk add --no-cache nginx fcgiwrap oksh openssl coreutils jq curl tcpdump

WORKDIR /app

RUN ln /usr/bin/oksh /bin/ksh
RUN mkdir /app/config
RUN mkdir -m 775 /app/logs
RUN chown nginx:nginx /app/logs
RUN mkdir -m 755 /app/html
RUN chown nginx:nginx /app/html

FROM builder as acmecgi
ARG NAME="ACME.cgi"
ARG VER="0.2.1"

RUN mkdir /app/cgi-bin
RUN mkdir -p -m 775 /app/data/pca
RUN mkdir -p -m 775 /app/data/acme
RUN chown nginx:nginx /app/data/pca
RUN chown nginx:nginx /app/data/acme

# copy the local file to save on bandwidth.  esp. while testing the image
ADD https://github.com/mgraves00/pca/archive/refs/tags/v1.7.tar.gz .
RUN <<EOF
tar -xzf v1.7.tar.gz
cp pca-1.7/pca /usr/bin/pca
rm -rf pca-1.7
EOF
#COPY pca-1.7/pca /usr/bin/pca
# install ACME
COPY --chmod=755 tmp/ACME.cgi cgi-bin/ACME.cgi
COPY --chmod=755 tmp/ACME_helper.sh cgi-bin/ACME_helper.sh
COPY --chmod=755 tmp/ACME_cleaner.sh cgi-bin/ACME_cleaner.sh
# install ACME config
COPY files/ACME.conf.dist .
COPY files/ACME_helper.conf.dist .
# config nginx
COPY files/nginx.conf nginx.conf.dist
COPY files/fastcgi_params fastcgi_params.dist

COPY files/index.html index.html.dist
COPY --chmod=755 files/gen_ca_html.sh gen_ca_html.sh

# copy entry
COPY --chmod=755 files/entrypoint.sh entrypoint.sh

# Ports
EXPOSE 8443/tcp

# Volumes
VOLUME /app/data

#ENTRYPOINT ["/bin/ash"]
ENTRYPOINT ["/app/entrypoint.sh"]

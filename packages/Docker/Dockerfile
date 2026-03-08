#
FROM docker.io/library/alpine:latest@sha256:25109184c71bdad752c8312a8623239686a9a2071e8825f20acb8f2198c3f659 AS builder

RUN apk add --no-cache nginx nfdump fcgiwrap oksh coreutils

#WORKDIR /app

RUN ln /usr/bin/oksh /bin/ksh
#RUN mkdir -m 775 flow-data
#RUN chown nginx:nginx flow-data
RUN mkdir config
RUN mkdir -m 775 logs
RUN chown nginx:nginx logs
RUN mkdir html
RUN chown nginx:nginx html

FROM builder as acmecgi
ARG NAME="ACME.cgi"
ARG VER="0.1"
WORKDIR /app
RUN mkdir -p /app/pca

COPY ACME.conf.dist ACME.conf.dist
COPY ACME_helper.conf.dist ACME.conf.dist

# copy the local file to save on bandwidth.  esp. while testing the image
#ADD https://github.com/mgraves00/pca/archive/refs/tags/v1.6.tar.gz .
COPY v1.6.tar.gz .
RUN <<EOF
tar -xzf v1.6.tar.gz
EOF

COPY nginx.conf nginx.conf.dist
COPY --chmod=755 entrypoint.sh entrypoint.sh

EXPOSE 8443/tcp

#ENTRYPOINT ["/bin/ash"]
ENTRYPOINT ["/app/entrypoint.sh"]


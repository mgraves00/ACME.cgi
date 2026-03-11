# ACME.cgi

## Description
ACME.cgi is a CGI script that implements RFC8555 ACME standard for certificate
issuance.  It utilizes and external program for the certificate request signing
and certificate revocation.

## Features
- ACME protocol server written **purely in Shell**.  Makes use of standard shell applications.
- Full ACME protocol implementation (coming with v1.0)
- Supports ECDSA certificates
- Supports SAN certificates (wildcard coming with v1.0)
- Simple setup.
- Docker ready
- IPv6 ready
- integrates with PCA for certificate support

## Tested with
- acme.sh
- acme-client

## Setup
### Standalone
1. Copy ACME.cgi, ACME_helper.sh and ACME_cleaner.sh to your web_root/cgi-bin directory and **chmod 555** the files.
2. Enable CGI listener.
3. Configure the web server to direct '/acme/*' to CGI listener. (see examples/ directory)
4. Create the web_root/acme directory.  Make sure it is writable by the web user/group.
5. Copy the *.conf files to a path accessible by the web server.  Suggest: web_root/etc
6. Setup cron to run ACME_cleaner.sh every 24 hours.

If web server is in a chroot environment:
1. Copy the following files into the chroot directory. Prog: jq, od, rm, tr, wc, cat, cut, sed, date, fold, openssl, sleep, uname, printf, mktemp, host, ftp/curl
2. Update the *.conf files to account for web_root/ path.

### Docker
1. Download release. Change directory to packages/Docker.
2. Run **make build** to build docker file.
3. Copy env.example to .env and configure to meet your requirements.
4. Run **docker-compose up -d** to start daemon.


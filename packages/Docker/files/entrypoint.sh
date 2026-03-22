#!/bin/ash

# verify the PCA is setup
echo -n "checking PCA..."
v=`pca | head -1 | cut -f2 -d" "`
if [ $? -ne 0 ]; then
	echo "pca not working"
	exit 1
fi
echo "found version $v"

ISSUER_DOMAIN=${SERVER_NAME:-""}
ISSUER_EMAIL=${CONTACT_EMAIL:-""}
ISSUER_URL=${SERVER_URL:-""}
ACME_LOG=${ACME_LOG:-/app/logs/acme.log}
ACME_DIR=${ACME_DIR:-/app/data/acme}
NONCE_EXPIRE=${NONCE_EXPIRE:-60}
MAX_CERT_DAYS=${MAX_CERT_DAYS:-90}
CLIENT_RETRY=${CLIENT_RETRY:-3}
ORDER_EXPIRE=${ORDER_EXPIRE:-300}
VERIFY_TIMEOUT=${VERIFY_TIMEOUT:-5}
VERIFY_RETRIES=${VERIFY_RETRIES:-2}
VERIFY_DELAY=${VERIFY_DELAY:-2}
CA_HELPER=${CA_HELPER:-/app/cgi-bin/ACME_helper.sh}
CA_NAME=${CA_NAME:-example}
PCA_ROOT=${PCA_ROOT:-/app/data/pca}
SERVER_SECRET=${SERVER_SECRET:-changeme}
if [ -z ${CA_NAME} ]; then
	echo "CA_NAME not specified"
	exit 1
fi
if [ -z ${ISSUER_DOMAIN} -o -z ${ISSUER_EMAIL} ]; then
	echo "missing ISSUER_DOMAIN or ISSUER_EMAIL or ISSUER_URL"
	exit 1
fi
if [ ! -d "${PCA_ROOT}/${CA_NAME}" ]; then
	echo "initializeing PCA"
	mkdir ${PCA_ROOT}
	pca ${CA_NAME} init
	pca ${CA_NAME} config set macros -key PUBLICURL -value http://${ISSUER_DOMAIN}/ca
	pca ${CA_NAME} config set macros -key PATHLEN -value 2
	pca ${CA_NAME} config set prog -name prog_ca -a -key copy_extensions -value CopyAll
	pca ${CA_NAME} config set ext -name extension_acme -a -key basicConstraints -value critical,CA:FALSE
	pca ${CA_NAME} config set ext -name extension_acme -a -key keyUsage -value nonRepudiation,digitalSignature
	pca ${CA_NAME} config set ext -name extension_acme -a -key subjectKeyIdentifier -value hash
	pca ${CA_NAME} config set ext -name extension_acme -a -key authorityKeyIdentifier -value keyid
	pca ${CA_NAME} config set ext -name extension_acme -a -key extendedKeyUsage -value serverAuth,clientAuth
	pca ${CA_NAME} config set pol -name policy_sign -key commonName -value optional
	echo "creating Root cert"
	pca ${CA_NAME} create root -days 4000 -bits 4096 -cn "${CA_NAME} Root CA"
	echo "creating ACME RA cert"
	pca ${CA_NAME} create req -name ACME_RA -days 3650 -newkey 4096 -cn "${CA_NAME} ACME RA"
	pca ${CA_NAME} sign -name ACME_RA -sign
	echo "setting ACME_RA as signing cert"
	pca ${CA_NAME} config sign -name ACME_RA
	chown -R nginx:nginx ${PCA_ROOT}
	[[ -d config/certs ]] || mkdir config/certs
fi
if [ ! -f "config/certs/server.crt" ]; then
	_a=`pca ${CA_NAME} show cert -name ${ISSUER_DOMAIN}`
	if [ -z "${_a}" ]; then
		echo "creating ${ISSUER_DOMAIN} cert"
		pca ${CA_NAME} create req -name ${ISSUER_DOMAIN} -newkey 2048 -cn "${ISSUER_DOMAIN}" -san "DNS=${ISSER_DOMAIN}"
		pca ${CA_NAME} sign -name ${ISSUER_DOMAIN} -days 365
	fi
	echo "exporting ${ISSUER_DOMAIN} cert"
	pca ${CA_NAME} create chain
	pca ${CA_NAME} export pkcs12 -name ${ISSUER_DOMAIN} -file config/certs/${ISSUER_DOMAIN}.p12 -pass ${SERVER_SECRET} -chain -overwrite
	echo -n "${SERVER_SECRET}" > /app/server.pass
	echo -n "${SERVER_SECRET}" > /app/key.pass
	openssl pkcs12 -in config/certs/${ISSUER_DOMAIN}.p12 -nocerts -out config/certs/server.key -passin file:/app/server.pass -passout file:/app/key.pass
	openssl pkcs12 -in config/certs/${ISSUER_DOMAIN}.p12 -nokeys -clcerts -out config/certs/server.crt -passin file:/app/server.pass
	openssl pkcs12 -in config/certs/${ISSUER_DOMAIN}.p12 -nokeys -cacerts -out config/certs/acme-roots.pem -passin file:/app/server.pass
	cat config/certs/server.crt config/certs/acme-roots.pem > config/certs/server.fullchain.pem
	rm -f /app/key.pass
fi

if [ ! -d "${ACME_DIR}" ]; then
	echo "initializeing ACME"
	mkdir ${ACME_DIR}
	mkdir ${ACME_DIR}/accts
	mkdir ${ACME_DIR}/certs
	mkdir ${ACME_DIR}/orders
	mkdir ${ACME_DIR}/challenges
	mkdir ${ACME_DIR}/nonce
	chown -R nginx:nginx ${ACME_DIR}
fi
if [ ! -h /etc/periodic/daily/ACME_cleaner.sh ]; then
	ln -sf /app/cgi-bin/ACME_cleaner.sh /etc/periodic/daily/ACME_cleaner.sh
fi

# always (re)create the html files
echo "creating html files"
/app/gen_ca_html.sh
if [ ! -h /etc/periodic/daily/gen_ca_html.sh ]; then
	ln -sf /app/gen_ca_html.sh /etc/periodic/daily/gen_ca_html.sh
fi

# initialize configs... if not there
if [ ! -f "/app/config/ACME.conf" ]; then
	echo "setting up /app/config/ACME.conf"
	cp /app/ACME.conf.dist /app/config/ACME.conf
	sed -i "s,@@ISSUER_DOMAIN@@,${ISSUER_DOMAIN}," /app/config/ACME.conf
	sed -i "s,@@ISSUER_EMAIL@@,${ISSUER_EMAIL}," /app/config/ACME.conf
	sed -i "s,@@ISSUER_URL@@,${ISSUER_URL}," /app/config/ACME.conf
	sed -i "s,@@ACME_LOG@@,${ACME_LOG}," /app/config/ACME.conf
	sed -i "s,@@ACME_DIR@@,${ACME_DIR}," /app/config/ACME.conf
	sed -i "s,@@NONCE_EXPIRE@@,${NONCE_EXPIRE}," /app/config/ACME.conf
	sed -i "s,@@ORDER_EXPIRE@@,${ORDER_EXPIRE}," /app/config/ACME.conf
	sed -i "s,@@MAX_CERT_DAYS@@,${MAX_CERT_DAYS}," /app/config/ACME.conf
	sed -i "s,@@CLIENT_RETRY@@,${CLIENT_RETRY}," /app/config/ACME.conf
	sed -i "s,@@OEDER_EXPIRE@@,${OEDER_EXPIRE}," /app/config/ACME.conf
	sed -i "s,@@VERIFY_TIMEOUT@@,${VERIFY_TIMEOUT}," /app/config/ACME.conf
	sed -i "s,@@VERIFY_RETRIES@@,${VERIFY_RETRIES}," /app/config/ACME.conf
	sed -i "s,@@VERIFY_DELAY@@,${VERIFY_DELAY}," /app/config/ACME.conf
	sed -i "s,@@CA_HELPER@@,${CA_HELPER}," /app/config/ACME.conf
	chown nginx:nginx /app/config/ACME.conf
fi
if [ ! -f "/app/config/ACME_helper.conf" ]; then
	echo "setting up /app/config/ACME_helper.conf"
	cp /app/ACME_helper.conf.dist /app/config/ACME_helper.conf
	sed -i "s,@@CA_NAME@@,${CA_NAME}," /app/config/ACME_helper.conf
	sed -i "s,@@PCA_ROOT@@,${PCA_ROOT}," /app/config/ACME_helper.conf
	chown nginx:nginx /app/config/ACME_helper.conf
fi
if [ ! -f "/app/config/nginx.conf" ]; then
	echo "setting up /app/config/nginx.conf"
	cp /app/nginx.conf.dist /app/config/nginx.conf
	cp /app/fastcgi_params.dist /app/config/fastcgi_params
	chown nginx:nginx /app/config/nginx.conf
	chown nginx:nginx /app/config/fastcgi_params
fi

# start crond
crond -b

# start fcgiwrap
echo -n "starting fcgiwrap..."
/usr/bin/fcgiwrap -c 5 -s tcp:127.0.0.1:9000 &
echo "done"

# start  nginx
echo "starting nginx..."
/usr/sbin/nginx -p /app -c /app/config/nginx.conf -g 'daemon off;'
#/usr/sbin/nginx -p /app -c /app/config/nginx.conf
echo "nginx exited: $?"
# nginx exited

# stop fcgiwrap
echo -n "Stopping fcgiwrap..."
pkill fcgiwrap
echo "done."


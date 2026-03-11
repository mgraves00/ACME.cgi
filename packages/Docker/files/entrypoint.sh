#!/bin/ash

# verify the PCA is setup

echo "checking PCA..."
v=`pca version`
if [ $? -ne 0 ]; then
	echo "pca not working"
	exit 1
fi
echo "found version $v"

# handle config
# copy 
if [ ! -f "/app/config/ACME.conf" ]; then
	echo "setting up /app/config/ACME.conf"
	cp ACME.conf.dist /app/config/ACME.conf
	sed -i "s/@@ISSUER_DOMAIN@@/${ISSUER_DOMAIN}/" /app/config/ACME.conf
	sed -i "s/@@ISSUER_EMAIL@@/${ISSUER_EMAIL}/" /app/config/ACME.conf
	chown nginx:nginx /app/config/ACME.conf
fi
if [ ! -f "/app/config/ACME_handler.conf" ]; then
	echo "setting up /app/config/ACME_handler.conf"
	cp ACME_handler.conf.dist /app/config/ACME_handler.conf
	sed -i "s/@@CA_NAME@@/${CA_NAME}/" /app/config/ACME_handler.conf
	chown nginx:nginx /app/config/ACME_handler.conf
fi

# start fcgiwrap
echo -n "starting fcgiwrap..."
/usr/bin/fcgiwrap -c 10 -s tcp:127.0.0.1:9000 &
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


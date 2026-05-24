#!/bin/ksh

TF=`mktemp`
export PCA_ROOT="/var/www/etc/pca"
CA_NAME="brainfat"
PCA=$(command -v pca) || { echo "cannot find PCA"; exit 1; }

now=`TZ=GMT date -j +"%s"`
${PCA} ${CA_NAME}  show cert -client -expire >$TF
cat $TF | sed -r 's/^(.*): notAfter=(.*)$/\1 \2/' | while read device exptime; do
        epoch=`TZ=GMT date -j -f "%b %e %H:%M:%S %Y %Z" +"%s" "${exptime}"`
		if [ $epoch -lt $now ]; then
			echo -n "cleaning up $device ..."
			${PCA} ${CA_NAME} revoke -name $device
			${PCA} ${CA_NAME} del cert -name $device
			${PCA} ${CA_NAME} del req -name $device
			echo "done"
		fi
done

rm -f $TF

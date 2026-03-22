#!/bin/ksh

# BSD 2-Clause License
# 
# Copyright (c) 2026, Michael Graves <mg@brainfat.net>
# All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
# 
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

PCA=$(which pca)
OSSL=$(which openssl)
CUT=$(which cut)

find_conf() {
	local _f
	for _f in "/etc/ACME_helper.conf" "/app/config/ACME_helper.conf"; do
		if [ -f "${_f}" ]; then
			echo ${_f}
			return
		fi
	done
	echo ""
}

conf=$(find_conf)
if [ -z "${conf}" ]; then
	echo "Status: 500 config not found"
	exit 1
else
	. "${conf}"
fi

PROG_NAME=${0##*/}
CA_NAME=${CA_NAME:-""}
PCA_ROOT=${PCA_ROOT:-"/etc/pca"}
DEFAULT_DAYS=${DEFAULT_DAYS:-90}
DEVNUL=${DEVNUL:-"/dev/null"}

# send all stderr to DEVNUL file
exec 2>>"${DEVNUL}"

if [ $# -lt 1 ]; then
	echo "${PROG_NAME} <command> <options>"
	echo "Commands:"
	echo "  sign <request_file> <cert_file> [days]"
	echo "  revoke <cert_to_revoke> [reason number]"
	exit 1
fi
CMD=$1; shift
case "$CMD" in
	"sign")
		REQFILE=$1; shift
		CRTFILE=$1; shift
		DAYS=${1:-${DEFAULT_DAYS}}
		REQNAME=${REQFILE##*/}
		REQNAME=${REQNAME%%.req}
		if [ ! -f "${REQFILE}" ]; then
			echo "${PROG_NAME}: cannot find request file ${REQFILE}"
			exit 1
		fi
		if [ -z "${CRTFILE}" ]; then
			echo "${PROG_NAME}: certificate file not specified"
			exit 1
		fi
		# import req
		PCA_ROOT=${PCA_ROOT} ${PCA} "${CA_NAME}" import request -name "${REQNAME}" -file "${REQFILE}" 2>&1
		if [ $? -ne 0 ]; then
			echo "${PROG_NAME}: error importing request"
			exit 1
		fi
		# sign req
		PCA_ROOT=${PCA_ROOT} ${PCA} "${CA_NAME}" sign -days "${DAYS}" -name "${REQNAME}" -ext extension_acme 2>&1
		if [ $? -ne 0 ]; then
			echo "${PROG_NAME}: error signing request"
			exit 1
		fi
		# extract the CERT
		PCA_ROOT=${PCA_ROOT} ${PCA} "${CA_NAME}" export cert -name "${REQNAME}" -file "${CRTFILE}" -overwrite -chain 2>&1
		if [ $? -ne 0 ]; then
			echo "${PROG_NAME}: error exporting cert"
			exit 1
		fi
		;;
	"revoke")
		CRTFILE=$1; shift
		local _serial
		local _out
		_serial=$(${OSSL} x509 -in "${CRTFILE}" -noout -serial | ${CUT} -f2 -d=)
		if [ $? -ne 0 -o -z "${_serial}" ]; then
			echo "${PROG_NAME}: error extracting serial"
			exit 1
		fi
		_out=$(PCA_ROOT=${PCA_ROOT} ${PCA} "${CA_NAME}" revoke -serial "${_serial}" 2>&1)
		if [ $? -ne 0 ]; then
			# filter out all except the "error" line
			echo "${PROG_NAME}: error revoke: ${_out}"
			exit 1
		fi
		;;
	*)
		echo "${PROG_NAME}: unknown command: $CMD"
		exit 1
		;;
esac

exit 0

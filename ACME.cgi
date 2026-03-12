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

# --- EXTERNAL PROGS ---
JQ=$(which jq)
OD=$(which od)
RM=$(which rm)
TR=$(which tr)
WC=$(which wc)
CAT=$(which cat)
CUT=$(which cut)
SED=$(which sed)
DATE=$(which date)
FOLD=$(which fold)
OSSL=$(which openssl)
SLEEP=$(which sleep)
UNAME=$(which uname)
PRINTF=$(which printf)
MKTEMP=$(which mktemp)
DNSLOOKUP=$(which host)
HTTPLOOKUP=$(which curl)
DEVNUL="/tmp/acme.discard"

# --- GLOBAL VARS ---
_HEADERS=
_BODY=""
_REQ_FILE=""
_JWK64=""

# --- FUNCTIONS ---
find_conf() {
	local _f
	for _f in "/etc/ACME.conf" "/app/config/ACME.conf"; do
		if [ -f "${_f}" ]; then
#			echo "using config: ${_f}" >&2
			echo "${_f}"
			return
		fi
	done
	echo ""
}

log_debug() {
    if [ "$DEBUG" = "1" ]; then
		log "DEBUG" "$*"
    fi
}

log() {
	local _sev=$1; shift;
    echo "$(${DATE}) [${_sev}] $*" >>"$LOG_FILE"
}

hc_string() {
	local _hc=$1
	case "${_hc}" in
		200) echo "OK";;
		201) echo "Created";;
		400) echo "Bad Request";;
		401) echo "Unauthorized";;
		402) echo "Payment Required";;
		403) echo "Forbidden";;
		404) echo "Not Found";;
		405) echo "Method Not Found";;
		406) echo "Not Acceptable";;
		407) echo "Proxy Authentication Required";;
		408) echo "Request Timeout";;
		409) echo "Conflict";;
		410) echo "Gone";;
		411) echo "Length Required";;
		412) echo "Precondition Failed";;
		413) echo "Content Too Long";;
		414) echo "URI Too Long";;
		415) echo "Unsupported Media Type";;
		416) echo "Range Not Satisfiable";;
		417) echo "Expecctation Failed";;
		418) echo "I'm a teaport";;
		421) echo "Misdirected Request";;
		422) echo "Unprocessable Content";;
		423) echo "Locked";;
		424) echo "Failed Dependency";;
		425) echo "Too Early";;
		426) echo "Upgrade Required";;
		428) echo "Precondition Required";;
		429) echo "Too Many Requests";;
		431) echo "Request Header Fields Too Large";;
		451) echo "Unavailable For Legal Reasons";;
		500) echo "Internal Server Error";;
		501) echo "Not Implemented";;
		502) echo "Bad Gateway";;
		503) echo "Service Unavailable";;
		504) echo "Gateway Timeout";;
		505) echo "HTTP Version Not Supported";;
		506) echo "Variant Also Negotiates";;
		507) echo "Insufficient Storage";;
		508) echo "Loop Detected";;
		510) echo "Not Exteneded";;
		511) echo "Network Authentication Required";;
		*) echo "";;
	esac
}

err_to_hc() {
	local _e=$1
	case "${_e}" in
		accountDoesNotExist)	echo 404;;
		alreadyRevoked)			echo 400;;
		badCSR)					echo 400;;
		badNonce)				echo 400;;
		badPublicKey)			echo 400;;
		badRevocationReason)	echo 406;;
		badSignatureAlgorithm)	echo 406;;
		caa)					echo 400;;
		compound)				echo 400;;
		connection)				echo 400;;
		dns)					echo 400;;
		externalAccountRequired)echo 400;;
		incorrectResponse)		echo 400;;
		invalidContact)			echo 400;;
		malformed)				echo 400;;
		orderNotReady)			echo 425;;
		rateLimited)			echo 429;;
		rejectedIdentifier)		echo 406;;
		serverInetrnal)			echo 500;;
		tls)					echo 400;;
		unauthorized)			echo 401;;
		unsupportedContact)		echo 400;;
		unsupportedIdentifier)	echo 400;;
		userActionRequired)		echo 403;;
		# custom ones
		notImplemented)			echo 501;;
		*) echo "";;
	esac
}

clean_content() {
	if [ ! -z "${_REQ_FILE}" -a -f "${_REQ_FILE}" ]; then
		${RM} -f "${_REQ_FILE}"
	fi
}

rfc3339_to_epoch() {
	local _e
	if [ -z "$1" ]; then
		echo "0"
		return
	fi
	case $(${UNAME}) in
		Linux)
			_e=`${DATE} +"%s" -d "$1"`
			;;
		*)
			_e=`${DATE} -j -f "%Y-%m-%dT%H:%M:%S%z" +"%s" "$1"`
			;;
	esac
	if [ -z "${_e}" ]; then
		echo "0"
	fi
	echo "${_e}"
}
epoch_to_rfc3339() {
	local _o
	if [ -z "$1" ]; then
		echo ""
		return
	fi
	case $(${UNAME}) in
		Linux)
			_e=`${DATE} +"%Y-%m-%dT%H:%M:%SZ" -d "@$1"`
			;;
		*)
			_o=`${DATE} -j -r "$1" +"%Y-%m-%dT%H:%M:%SZ"`
#			_o=`${DATE} -j -r "$1" +"%Y-%m-%dT%H:%M:%S%z"`
			;;
	esac
	echo "${_o}"
}

get_epoch() {
	local _e
	case $(${UNAME}) in
		Linux)
			_e=`${DATE} +"%s"`
			;;
		*)
			_e=`${DATE} -j +"%s"`
			;;
	esac
	echo "${_e}"
}

_der_len() {
    local n=$1
    if   [ "$n" -lt 128 ]; then ${PRINTF} "%02x"  "$n"
    elif [ "$n" -lt 256 ]; then ${PRINTF} "81%02x" "$n"
    else                        ${PRINTF} "82%04x" "$n"
    fi
}
_der_seq() {
    local p=$1; local len=$(( ${#p} / 2 ))
    ${PRINTF} "30%s%s" "$(_der_len "$len")" "$p"
}
_der_int() {
    local hex=$1
	local len
	# remove leading zero bytes
	while [ "${#hex}" -gt 2 ] && [ $(echo -n "${hex}" | cut -c1-2) == "00" ]; do
		hex=$(echo -n "${hex}" | cut -c3-)
	done
	# if high bit set, prepend 00 so integer stays positive
	[ $(( 0x$(echo -n "$hex" | cut -c1-2) )) -ge 128 ] && hex="00${hex}"
    len=$(( ${#hex} / 2 ))
    ${PRINTF} "02%s%s" "$(_der_len "$len")" "$hex"
}
_der_bitstring() {
    local inner="00$1"; local len=$(( ${#inner} / 2 ))
    ${PRINTF} "03%s%s" "$(_der_len "$len")" "$inner"
}
_der_octetstring() {
    local len=$(( ${#1} / 2 ))
    ${PRINTF} "04%s%s" "$(_der_len "$len")" "$1"
}
_der_oid() {
    local len=$(( ${#1} / 2 ))
    ${PRINTF} "06%s%s" "$(_der_len "$len")" "$1"
}
_der_ctx0() {
    local len=$(( ${#1} / 2 ))
    ${PRINTF} "a0%s%s" "$(_der_len "$len")" "$1"
}
_der_ctx1() {
    local len=$(( ${#1} / 2 ))
    ${PRINTF} "a1%s%s" "$(_der_len "$len")" "$1"
}
_hex_pad() {
    local hex=$1 target=$(( $2 * 2 ))
    while [ ${#hex} -lt "$target" ]; do hex="00${hex}"; done
    ${PRINTF} "%s" "$hex"
}
# variables cannot store null bytes. this means we can only pass the data thru
_bin_to_hex() {
#	local _s=$1
#	if [ ${#_s} -eq 0 ]; then
#		_s=$(${CAT})
#	fi
#	echo -n "$_s" | ${OD} -A n -v -t x1 | ${TR} -d '\r\t\n '
	${OD} -A n -v -t x1 | ${TR} -d '\r\t\n '
}
#NOTE: outputs binary stream
_hex_to_bin() {
	local _s=$1
	local _h
	if [ ${#_s} -eq 0 ]; then
		_s=$(${CAT})
	fi
	for _h in $(echo -n "$_s" | ${SED} 's/\([0-9a-fA-F]\{2\}\)/ \1/g'); do
		${PRINTF} "\x${_h}"
	done
}
_b64url_to_hex() {
	${PRINTF} "%s" "$1" | url_unprotect | ${OSSL} enc -a -A -d | _bin_to_hex
}
_hex_to_pem() {
	local _hex=$1
	local _label=$2
	echo "-----BEGIN ${_label}-----"
	${PRINTF} "%s" "${_hex}" | _hex_to_bin | ${OSSL} enc -a -A | ${FOLD} -w 64
	echo ""
	echo "-----END ${_label}-----"
}
# rsaEncryption          1.2.840.113549.1.1.1
_OID_RSA="2a864886f70d010101"
# id-ecPublicKey         1.2.840.10045.2.1
_OID_EC_PUB="2a8648ce3d0201"
# prime256v1 / P-256     1.2.840.10045.3.1.7
_OID_P256="2a8648ce3d030107"
# secp384r1  / P-384     1.3.132.0.34
_OID_P384="2b81040022"
# secp521r1  / P-521     1.3.132.0.35
_OID_P521="2b81040023"
_jwk_rsa_public_pem() {
    local n_hex e_hex
    n_hex=$(_b64url_to_hex "$1")
    e_hex=$(_b64url_to_hex "$2")
    # PKCS#1 RSAPublicKey ::= SEQUENCE { INTEGER n, INTEGER e }
    local rsa_pub
    rsa_pub=$(_der_seq "$(_der_int "$n_hex")$(_der_int "$e_hex")")
    # AlgorithmIdentifier ::= SEQUENCE { OID rsaEncryption, NULL }
    local alg
    alg=$(_der_seq "$(_der_oid "$_OID_RSA")0500")
    # SubjectPublicKeyInfo ::= SEQUENCE { AlgorithmIdentifier, BIT STRING }
    _hex_to_pem "$(_der_seq "${alg}$(_der_bitstring "$rsa_pub")")" "PUBLIC KEY"
}
_jwk_ec_public_pem() {
    local crv=$1 x=$2 y=$3
    local curve_oid sz
    case "$crv" in
        P-256) curve_oid="$_OID_P256"; sz=32 ;;
        P-384) curve_oid="$_OID_P384"; sz=48 ;;
        P-521) curve_oid="$_OID_P521"; sz=66 ;;
        *) ${PRINTF} "Error: unsupported EC curve '%s'\n" "$crv" >&2; return 1 ;;
    esac
    local x_hex y_hex
    x_hex=$(_hex_pad "$(_b64url_to_hex "$x")" "$sz")
    y_hex=$(_hex_pad "$(_b64url_to_hex "$y")" "$sz")
    # Uncompressed EC point: 04 || x || y
    local point="04${x_hex}${y_hex}"
    local alg
    alg=$(_der_seq "$(_der_oid "$_OID_EC_PUB")$(_der_oid "$curve_oid")")
    _hex_to_pem "$(_der_seq "${alg}$(_der_bitstring "$point")")" "PUBLIC KEY"
}

#NOTE: outputs binary stream.
sig_to_der() {
	local _s=$1; shift
	local _b=${1:-ES256}
	local _sz=0
	local h1 h2
	if [ -z "${_s}" ]; then
		log_debug "s2d: unable to read string"
		return 1
	fi
	_s=$(echo -n "$_s" | url_unprotect | ${OSSL} enc -a -A -d | _bin_to_hex)
	case "${_b}" in
		ES256)
			if [ ${#_s} -ne 128 ]; then
				log_debug "invalid signature size 128 != ${#_s}"
				return 1
			fi
			_sz=64
			;;
		ES384)
			if [ ${#_s} -ne 192 ]; then
				log_debug "invalid signature size 192 != ${#_s}"
				return 1
			fi
			_sz=96
			;;
		ES521)
			if [ ${#_s} -ne 264 ]; then
				log_debug "invalid signature size 264 != ${#_s}"
				return 1
			fi
			_sz=132
			;;
		RS*)
			_sz=${_b##RS}
			;;
		*)
			log_debug "s2b unsupported hash"
			return 1
			;;
	esac
	if [ ${_sz} -eq 0 ]; then
		log_debug "s2b size not set"
		return 1
	fi
	case "${_b}" in
		ES*)
			h1=`echo -n "${_s}" | ${CUT} -c1-${_sz}`
			h2=`echo -n "${_s}" | ${CUT} -c$((${_sz}+1))-`
			_s=$(_der_seq $(_der_int ${h1})$(_der_int ${h2}))
			;;
		RS*)
			# just output signature
			;;
	esac
	# now output signature in DER format
	echo -n "${_s}" | _hex_to_bin
}

extract_id() {
	local _id=${1:-${REQUEST_URI}}
	local _r=${_id##*/}
	local _cmp=`echo -n "$_r" | ${SED} -nr '/^[a-zA-Z0-9_-]+$/p'`
	if [ -z "${_cmp}" ]; then
		log_debug "extract_id: error id: '$_r'"
		return_error 400 "malformed" "invalid id"
		# no return
	fi
	echo "${_r}"
}

read_content() {
	local _sz
	local _encstr
	if [ ! -z "${CONTENT_LENGTH}" ]; then
		_REQ_FILE=`${MKTEMP} -t "acme-XXXXXX.json"`
		if [ $? -ne 0 ]; then
			log "ERROR" "read_content: error createing tmp file"
			return_error 500 "serverInternal" "error creating tmp file"
			# no return
		fi
		log_debug "read_content: _REQ_FILE=${_REQ_FILE}"
		${CAT} - >${_REQ_FILE}
		_sz=$(${CAT} ${_REQ_FILE} | ${WC} -c | ${TR} -d ' ')
		if [ "${CONTENT_LENGTH}" -ne "${_sz}" ]; then
			log "ERROR" "read_content: content_length: ${CONTENT_LENGTH} != content_size: ${_sz}"
			return_error 413 "malformed" "Content Size Mismatch"
			# no return
		fi
		# save the protect and payload in base64 for validating jwk
		_JWK64=$(${CAT} ${_REQ_FILE} | ${JQ} -cr '(.protected // "") + "." + (.payload // "")')
		# decode the base64 encodings
		_encstr=$(${CAT} ${_REQ_FILE} | ${JQ} -r '.protected = (.protected | @base64d | fromjson) | .payload = try (.payload | @base64d | fromjson) catch ""')
		if [ $? -ne 0 ]; then
			log "ERROR" "read_content: error decoding content"
			return_error  413 "malformed" "error decoding b64"
			# no return
		fi
		echo "${_encstr}" >${_REQ_FILE}
		if [ $? -ne 0 ]; then
			log "ERROR" "read_content: error saving content"
			return_error  413 "malformed" "error saving request"
			# no return
		fi
	fi
}

# see rfc8555 sec 6.1 and rfc4648 sec 5
url_protect() {
	local _s
	if [ $# -eq 0 ]; then
		_s=$(${CAT})
	else
		_s=$*
	fi
	echo -n "${_s}" | ${TR} '/+' '_-' | ${TR} -d '= '
}

# see rfc8555 sec 6.1 and rfc4648 sec 5
url_unprotect() {
	local _s
	if [ $# -eq 0 ]; then
		_s=$(${CAT})
	else
		_s=$*
	fi
	local _l=$((${#_s} % 4))
	if [ $_l -eq 2 ]; then
		_s="${_s}=="
	elif [ $_l -eq 3 ]; then
		_s="${_s}="
	fi
	echo -n "${_s}" | ${TR} '_-' '/+'
}

#NOTE: investigate a file locking scheme
set_file_field() {
	local _file=$1
	local _f=$2
	local _res
	if [ -z "${_file}" ]; then
		log_debug "set_file_filed: no file given"
		return 1
	fi
	if [ ! -f "${_file}" ]; then
		log_debug "set_file_field: no file ${_file}"
		return 1
	fi
	_res=`${CAT} ${_file} | ${JQ} -cr "${_f}"`
	if [ $? -ne 0 ]; then
		log_debug "set_file_field: error setting field ${_f} from ${_file}"
		return 1
	fi
	echo "${_res}" >${_file}
	if [ $? -ne 0 ]; then
		log_debug "set_file_field: error saving file ${_file}"
	fi
	return 0
}

query_file_field() {
	local _file=$1;
	local _f=$2;
	local _res
	if [ -z "${_file}" ]; then
		log_debug "query_file_field: no file given"
		echo ""
		return 1
	fi
	if [ ! -f "${_file}" ]; then
		log_debug "query_file_field: no file ${_file}"
		echo ""
		return 1
	fi
	_res=`${CAT} ${_file} | ${JQ} -cr "${_f}"`
	if [ $? -ne 0 ]; then
		log_debug "query_file_field: error fetching field ${_f} from ${_file}"
		echo ""
		return 1
	fi
	echo "${_res}"
	return 0
}

query_req_field() {
	local _f=$1
	local _rc
	local _res
	_res=`query_file_field "${_REQ_FILE}" "${_f}"`
	if [ $? -ne 0 ]; then
		return 1
	fi
	echo "${_res}"
	return 0
}

query_account_field() {
	local _n=$1
	local _f=$2
	local _rc
	local _res
	_res=`query_file_field "${ACME_DIR}/accts/${_n}" "${_f}"`
	if [ $? -ne 0 ]; then
		return 1
	fi
	echo "${_res}"
	return 0
}

query_order_field() {
	local _n=$1
	local _f=$2
	local _rc
	local _res
	_res=`query_file_field "${ACME_DIR}/orders/${_n}" "${_f}"`
	if [ $? -ne 0 ]; then
		return 1
	fi
	echo "${_res}"
	return 0
}

query_challenge_field() {
	local _n=$1
	local _f=$2
	local _rc
	local _res
	_res=`query_file_field "${ACME_DIR}/challenges/${_n}" "${_f}"`
	if [ $? -ne 0 ]; then
		return 1
	fi
	echo "${_res}"
	return 0
}

set_account_field() {
	local _n=$1
	local _f=$2
	local _rc
	local _res
	_res=`set_file_field "${ACME_DIR}/accts/${_n}" "${_f}"`
	if [ $? -ne 0 ]; then
		return 1
	fi
	return 0
}

set_order_field() {
	local _n=$1
	local _f=$2
	local _rc
	local _res
	_res=`set_file_field "${ACME_DIR}/orders/${_n}" "${_f}"`
	if [ $? -ne 0 ]; then
		return 1
	fi
	return 0
}

set_challenge_field() {
	local _n=$1
	local _f=$2
	local _rc
	local _res
	_res=`set_file_field "${ACME_DIR}/challenges/${_n}" "${_f}"`
	if [ $? -ne 0 ]; then
		return 1
	fi
	return 0
}

# see section 6.2
# validate the JSON Web Signature
validate_jws() {
	local _jwk64=$(echo -n "${_JWK64}" | ${TR} -d '\n\r\t ')
	local _kty
	local _crv
	local _sig
	local _pem
	local _sigfile
	local _pemfile
	local _acct
	local _alg
	local _hash
	_acct=`jwk_to_acct`
	if [ $? -ne 0 ]; then
		# jwk not in request... look for kid
		local _kid=`query_req_field '.protected | .kid // ""'`
		if [ -z "${_kid}" ]; then
			return 1
		fi
#		_acct=${_kid##*/}
		_acct=`extract_id "${_kid}"`
	fi
	if [ -z "${_acct}" ]; then
		# account not found
		return 1
	fi
	log "WARN" "validate_jws: looking up account: ${_acct}"
	_pemfile="${ACME_DIR}/accts/${_acct}.pem"
	_alg=`query_req_field '.protected | .alg'`
	if [ $? -ne 0 ]; then
		log_debug "validate_jws: failed get alg"
		return 1
	fi
	case "${_alg}" in
		*256) _hash="-sha256" ;;
		*384) _hash="-sha384" ;;
		*512) _hash="-sha512" ;;
		*)
			log "ERROR" "validate_jws: hash not supported: ${_alg}"
			return 1
			;;
	esac
	# if PEM file has not been created... create and save it.
	if [ ! -f "${_pemfile}" ]; then
		_kty=`query_req_field '.protected | .jwk | .kty'`
		if [ $? -ne 0 ]; then
			log_debug "validate_jws: failed get kty"
			return 1
		fi
		_crv=`query_req_field '.protected | .jwk | .crv'`
		if [ $? -ne 0 ]; then
			log_debug "validate_jws: failed get crv"
			return 1
		fi
		case "${_kty}" in
			EC)
				local _x
				local _y
				_x=`query_req_field '.protected | .jwk | .x // ""'`
				if [ $? -ne 0 -o -z "${_x}"]; then
					log_debug "validate_jws: failed get x"
					return 1
				fi
				_y=`query_req_field '.protected | .jwk | .y // ""'`
				if [ $? -ne 0 -o -z "${_y}"]; then
					log_debug "validate_jws: failed get y"
					return 1
				fi
				_pem=`_jwk_ec_public_pem "${_crv}" "${_x}" "${_y}"`
				if [ $? -ne 0 ]; then
					log_debug "validate_jws: generate EC PEM"
					return 1
				fi
				;;
			RSA)
				local _n
				local _e
				_n=`query_req_field '.protected | .jwk | .n // ""'`
				if [ $? -ne 0 -o -z "${_n}" ]; then
					log_debug "validate_jws: failed get n"
					return 1
				fi
				_e=`query_req_field '.protected | .jwk | .e // ""'`
				if [ $? -ne 0 -o -z "${_e}" ]; then
					log_debug "validate_jws: failed get e"
					return 1
				fi
				_pem=`_jwk_rsa_public_pem "${_n}" "${_e}"`
				if [ $? -ne 0 ]; then
					log_debug "validate_jws: generate RSA PEM"
					return 1
				fi
				;;
			*)	# unsupported type
				log "ERROR" "validate_jws: unsupported signature type: ${_kty}"
				return 1
				;;
		esac
		# save pem file for future
		echo -n "$_pem" > ${_pemfile}
		if [ $? -ne 0 ]; then
			log_debug "validate_jws: failed to save pem file"
			return 1
		fi
	else
		# Check to see if jwk was provided,
		# if it was compare with stored version.
		# If not we have already verified
		# the jwk and kid so just pass thru.
		local n o
		n=`query_req_field '.protected | .jwk // ""'`
		if [ ! -z "$n" ]; then
			o=`query_account_field "${_acct}" '.jwk'`
			if [ "$n" != "$o" ]; then
				echo "n: $n" >&2
				echo "o: $o" >&2
				return_error 500 "serverInternal" "old and new jwk don't match"
			fi
		fi
	fi
	_sig=`query_req_field '.signature'`
	if [ $? -ne 0 ]; then
		log "ERROR" "validate_jws: failed get signature"
		return 1
	fi
	_sigfile=`${MKTEMP} -t "acme-sig.XXXXXXX" 2>&1`
	if [ $? -ne 0 ]; then
		log_debug "validate_jws: failed to make temp file ${_sigfile}"
		return 1
	fi
	# save sig to file in DER format
	sig_to_der "${_sig}" "${_alg}" > ${_sigfile}
	if [ $? -ne 0 ]; then
		log_debug "validate_jws: failed to save signature to tmpfile"
		${RM} -f ${_sigfile}
		return 1
	fi
	# verify the signature
	_ret=`echo -n "${_jwk64}" | ${OSSL} dgst ${_hash} -verify ${_pemfile} -signature ${_sigfile}`
	if [ $? -ne 0 ]; then
		log "ERROR" "validate_jws: failed verify signature"
		log_debug "alg: ${_alg}"
		log_debug "jwk64: ${_jwk64}"
		log_debug "keyfile: $(${CAT} ${_pemfile})"
		log_debug "signature: $(${CAT} ${_sigfile} | ${OSSL} enc -a -A)"
		log_debug "validate_jws: signature verify failed: ${_ret}"
		#${CAT} ${_sigfile} | ${OSSL} asn1parse -inform DER -dump >&2
		${RM} -f ${_sigfile}
		return 1
	fi
	${RM} -f ${_sigfile}
	log "INFO" "validate_jws: verify success"
	return 0
}

set_header() {
	local _h=$1
	if [ -z "$_HEADERS" ]; then
		_HEADERS[0]="${_h}"
	else
		_HEADERS[${#_HEADERS[*]}]=${_h}
	fi
}

valid_target() {
	local _t=$1
	local _i
#XXX need to make more dynamic
#XXX resolve the host name
#XXX check for rfc1918 and link-local addresses
	for _i in "127.0.0.1 localhost 169.254.169.254"; do
		if [ "${_i}" == "${_t}" ]; then
			return 1
		fi
	done
	return 0
}

process_revoke() {
#	local _o=$1
	local _tmpfile
	local _reason
	local _rc=0
#	if [ -z "${_o}" ]; then
#		echo "process_csr: no order provided"
#		return 1
#	fi
	_reason=`query_req_field '.payload | .reason // ""'`
	if [ $? -ne 0 ]; then
		echo "process_revoke: looking for reason field failed"
		return 3
	fi
	_tmpfile=`${MKTEMP} -t "acme-revoke.XXXXXXXX"` || return 99
	# Must add the ---- to begginging and end, and unprotect the CERT and wrap
	# the lines on 64 character boundary
	echo "-----BEGIN CERTIFICATE-----" > ${_tmpfile}
	${CAT} ${_REQ_FILE} | ${JQ} -r '.payload | .certificate' | url_unprotect | ${FOLD} -w 64 >> ${_tmpfile}
	# make sure we are on a new line
	echo >> ${_tmpfile}
	echo "-----END CERTIFICATE-----" >> ${_tmpfile}
	_ret=$(${CA_HELPER} "revoke" ${_tmpfile} ${_reason})
	if [ $? -ne 0 ]; then
		echo "process_revoke: error revoking certificate: ${_ret}"
#		${CAT} ${_tmpfile} >&2
		${RM} -f ${_tmpfile}
		case "${_ret}" in
			*"Already revoke"*)
				_rc=1
				;;
			*"not found"*)
				_rc=2
				;;
			*)
				_rc=3
				;;
		esac
	fi
	${RM} -f ${_tmpfile}
	return ${_rc}	
}

process_csr() {
	local _o=$1
	local _ret
	if [ -z "${_o}" ]; then
		echo "process_csr: no order provided"
		return 1
	fi
	if [ ! -f ${ACME_DIR}/certs/${_o}.req ]; then
		echo "process_csr: csr file not found"
		return 1
	fi
	_ret=$(${CA_HELPER} "sign" ${ACME_DIR}/certs/${_o}.req ${ACME_DIR}/certs/${_o}.pem ${MAX_CERT_DAYS})
	if [ $? -ne 0 ]; then
		echo "process_csr: error signing CSR: ${_ret}"
		return 1
	fi
	return 0	
}

jwk_to_acct() {
	local _a
	_a=`query_req_field '.protected | .jwk // ""'`
	if [ -z "${_a}" ]; then
		return 1
	fi
	_a=`echo -n "${_a}" | ${TR} -d " " | ${OSSL} dgst -sha256 | cut -f2 -d' '`
	echo "${_a}"
	return 0
}

# output error to STDOUT
gen_thumbprint() {
	local _acct=$1
	local _ret
	local _jwk
	if [ -z "${_acct}" ]; then
		echo "account not specified"
		return 1
	fi
	_jwk=`query_account_field "${_acct}" '.jwk // ""'`
	if [ $? -ne 0 ]; then
		echo "error query_account_field"
		return 1
	fi
	if [ -z "${_jwk}" ]; then
		echo "failed to retrieve jwk"
		return 1
	fi
	_ret=`echo -n "${_jwk}" | ${TR} -d " " | ${OSSL} dgst -sha256 -binary | ${OSSL} base64 -a | url_protect`
	echo "${_ret}"
}

# See section 8.1
compare_token() {
	local _acct=$1; shift
	local _token=$1; shift
	local _cmp=$1; shift
	local _tmb
	_tmb=`gen_thumbprint "${_acct}"`
	if [ $? -ne 0 ]; then
		log_debug "compare_token: gen_thumbprint failed ${_tmb}"
		return 1
	fi
	if [ "${_token}.${_tmb}" == "${_cmp}" ]; then
		log_debug "compare_token: ${_token}.${_tmb} == ${_cmp}"
		return 0
	fi
	log_debug "compare_token: ${_token}.${_tmb} != ${_cmp}"
	return 1
}

process_http01_request() {
	local _host=$1
	local _acct=$2
	local _token=$3
	local _retry=${4:-1}
	local _delay=${5:-5}
	local _timout=${6:-5}
	local _rc=1
	local _resp
	local _tmpfile
	if [ -z "${_host}" -o -z "${_acct}" -o -z "${_token}" ]; then
		log_debug "process_http01_request: host or account or token empty"
		return 1
	fi
	_tmpfile=`${MKTEMP} -t "acme-challenge-${_host}.XXXXXXXX"` || return 99
	while [ ${_retry} -gt 0 ]; do
#		_resp=`${HTTPLOOKUP} -w ${_timout} -U "ACME.cgi challenge test" -o ${_tmpfile} "http://${_host}/.well-known/acme-challenge/${_token}" 2>&1`
		_resp=`${HTTPLOOKUP} --silent --connect-timeout ${_timout} -A "ACME.cgi challenge test" -o ${_tmpfile} "http://${_host}/.well-known/acme-challenge/${_token}" 2>&1`
		if [ $? -ne 0 ]; then
			log_debug "process_http01_request: error looking up record. ${_resp}"
			echo '{\"type\":\"connection",\"desc\":\"'${_resp}'\"}'
			# ok to loop
		else
			local _val=`${CAT} ${_tmpfile}`
			local x
			log_debug "process_http01_request: retreived value: ${_val}"
			x=`compare_token "${_acct}" "${_token}" "${_val}"`
			if [ $? -eq 0 ]; then
				_rc=0
				break;
			fi
			# retreive succeeded... but token match failed
			echo '{\"type\":\"incorrectResponse\",\"desc\":\"tokens do not match\"}'
			break;
		fi
		log_debug "process_http01_request: sleeping for ${_delay} retry ${_retry}"
		${SLEEP} ${_delay}
		_retry=$(($_retry-1))
	done
	${RM} -f ${_tmpfile}
	log_debug "process_http01_request: return ${_rc}"
	return ${_rc}
}

process_dns01_request() {
	local _host=$1
	local _acct=$2
	local _token=$3
	local _retry=${4:-1}
	local _delay=${5:-5}
	local _timout=${6:-5}
	local _rc=1
	local _resp
	if [ -z "${_host}" -o -z "${_token}" ]; then
		log_debug "process_dns01_request: host or token empty"
		return 1
	fi
	while [ ${_retry} -gt 0 ]; do
#XXX not correct... need to look for different DNS record
		_resp=`${DNSLOOKUP} -t TXT -W ${_timout} ${_host}`
		case "${_resp}" in
			*"not found"*)
				;;
			*"no TXT"*)
				;;
			*"descriptive text"*)
				_resp=$(echo "$_resp" | ${CUT} -f4 -d" " | ${TR} -d '"')
				if [ "${_resp}" == "${_token}" ]; then
					_rc=0
				fi
				return ${_rc}
				;;
		esac
		${SLEEP} ${_delay}
		_retry=$(($_retry-1))
	done
	return ${_rc}
}

process_challenge() {
	local _order=$1
	local _rc=0
	local _status
	local _acct
	local challenges
	local target
	log "INFO" "process_challenge: ${_order}"
	if [ ! -f "${ACME_DIR}/challenges/${_order}" ]; then
		log "ERROR" "process_challenge: cannot find challenge ${_order}"
		exit 0
	fi
	_status=`query_challenge_field "${_order}" '.status // ""'`
	if [ "${_status}" != "pending" ]; then
		log_debug "process_challenge: status ${_status}"
		log "INFO" "process_challenge: order ${_order} status ${_status}"
		exit 0
	fi
	set_challenge_field "${_order}" '.status = "processing"'
	if [ $? -ne 0 ]; then
		log_debug "failed to set status to processing"
		log "ERROR" "process_challenge: failed to set state of order ${_order} to processing"
		exit 0
	fi
	_acct=`echo "${_order}" | cut -f1 -d"_"`
	challenges=`query_challenge_field "${_order}" '.challenges[] | "\(.type):\(.status):\(.token)" // "" '`
	if [ -z "${challenges}" ]; then
		log "ERROR" "process_challenge: no challenges found for order ${_order}"
		exit 0
	fi
	target=`query_order_field "${_order}" '.identifiers[0] | .value // ""'`
	if [ -z "${target}" ]; then
		log "ERROR" "process_challenge: no target found in indentifer for order ${_order}"
		exit 0
	fi
	# sanitize target
	valid_target "${target}"
	if [ $? -ne 0 ]; then
		log "ERROR" "process_challenge: target ${target} on invalid list for order ${_order}"
		exit 0
	fi
	log_debug "process_challenge: challenges: ${challenges} for target ${target}"
	local i=0	
	for chal in ${challenges}; do
		local typ=`echo "$chal" |cut -f1 -d:`
		local chal_status=`echo "$chal" |cut -f2 -d:`
		local token=`echo "$chal" |cut -f3 -d:`
		if [ "${chal_status}" == "valid" ]; then
			# already validated the challenge...
			log_debug "process_challenge: challenge already validated. skipping"
			continue;
		fi
		case "$typ" in
#			"dns-01")
#				process_dns01_request "${target}" "${_acct}" "${token}" "${VERIFY_RETRIES}" "${VERIFY_DELAY}" "${VERIFY_TIMEOUT}"
#				if [ $? -ne 0 ]; then
#					log "WARN" "process_challenge: ${_order} ${val} failed"
#					_rc=1
#					break;
#				fi
#				log "INFO" "process_challenge: ${_order} ${val} success"
#				;;
			"http-01")
				local _ret
				_ret=`process_http01_request "${target}" "${_acct}" "${token}" "${VERIFY_RETRIES}" "${VERIFY_DELAY}" "${VERIFY_TIMEOUT}"`
				if [ $? -ne 0 ]; then
					set_challenge_field "${_order}" '.challenges['$i'].status = "invalid"'
					if [ $? -ne 0 ]; then
						log "ERROR" "process_challenge: failed to set challenge status to invalid after unsuccessful test"
						_rc=1
						break;
					fi
					set_challenge_field "${_order}" '.status = "invalid"'
					if [ $? -ne 0 ]; then
						log "ERROR" "process_challenge: failed to set challenge status to invalid after unsuccessful test"
						_rc=1
						break;
					fi
#XXX need way to take _ret from process_xxxx_request to .error = {}
#log_debug "_ret = ${_ret}"
#					set_challenge_field "${_order}" '.error = ("'${_ret}'" | fromjson)'
					set_challenge_field "${_order}" '.error = {"type":"connnect","desc":"error"}'
					if [ $? -ne 0 ]; then
						log "ERROR" "process_challenge: failed to set challenge error after unsuccessful test"
						_rc=1
						break;
					fi
					log "WARN" "process_challenge: ${_order} failed"
					_rc=1
					break;
				else
					set_challenge_field "${_order}" '.challenges['$i'].status = "valid"'
					if [ $? -ne 0 ]; then
						log "ERROR" "process_challenge: failed to set challenge status to valid after successful test"
						_rc=1
						break;
					fi
					set_challenge_field "${_order}" '.status = "valid"'
					if [ $? -ne 0 ]; then
						log "ERROR" "process_challenge: failed to set challenge status to valid after successful test"
						_rc=1
						break;
					fi
					set_challenge_field "${_order}" '.validated = "'$(epoch_to_rfc3339 $(get_epoch))'"'
					if [ $? -ne 0 ]; then
						log "ERROR" "process_challenge: failed to set challenge valiadted to time after successful test"
						_rc=1
						break;
					fi
				fi
				log "INFO" "process_challenge: ${_order} success"
				;;
			*)
				log "ERROR" "process_challenge error: unknown type ${typ}"
				_rc=1
				;;
		esac
		i=$(($i+1))
	done
#XXX this seems not right... perhaps need to use set_challenge_field()
	if [ ${_rc} -ne 0 ]; then
		log "ERROR" "process_challenge: error processing order"
#	else
#		local _t=$(${CAT} ${_REQ_FILE})
#		echo "${_t}" | ${JQ} -r '.status = "valid"' >${_REQ_FILE}
#		if [ $? -ne 0 ]; then
#			log "ERROR" "process_challenge error: cannot set status to valid"
#		fi
	fi
	log "INFO" "process_challenge end: ${_order}"
	exit 0
}

return_error() {
	local _hc=$1; shift
	local _ec=$1; shift
	local _msg=$*
	local _t=`err_to_hc $_ec`
	_ec=${_t:-$_ec}
	log "ERROR" "${_ec}: ${_msg}"
	set_header 'Content-Type: application/problem+json'
	_BODY='{"type":"urn:ietf:params:acme:error:'${_ec}'","detail":"'${_msg}'"}'
	log_debug "return_error: req: $(${CAT} ${_REQ_FILE})"
	return_result ${_hc} ""
	# no return
}

#DESC: output the return state, header and body(if any)
#NOTE: no return
return_result() {
	local _hc=$1; shift
	local _msg=$*
	local _len=0
	local _h
	# set the Link header
	set_header "Link: <${ISSUER_URL}/directory>;rel=\"index\""
	# return the HTTP status back to CGI interperter
	echo "Status: ${_hc} $(hc_string ${_hc})"
	# output the headers
	for _h in "${_HEADERS[@]}"; do
		echo "${_h}"
	done
# XXX this breaks things
#	echo "Content-Length: ${#_BODY}"
	echo
	# output a body if it exists
	if [ ${#_BODY} -gt 0 ]; then
#log_debug "body=${_BODY}"
		echo -n "${_BODY}"
	fi
	clean_content
	exit 0
}

# NOTE: check and create directories used to issue certs
# RETURN: 0 - success, 1 - failed
check_dirs() {
	local _dir=$1
	local _d
	local DIRS="$_dir $_dir/nonce $_dir/orders $_dir/certs $_dir/accts"
	for _d in $DIRS; do
		if [ ! -d "$_d" ]; then
			return 1
		fi	
	done
	return 0
}

check_post_as_get() {
	if [ -z "$REQUEST_METHOD" ]; then
		return 1
	fi
	if [ "$REQUEST_METHOD" != "POST" ]; then
		return 1
	fi
	return 0
}

check_url() {
	local _fun=$1
	local _rcvd_url=`query_req_field '.protected | .url'`
	local _exp_url=${ISSUER_URL}/${_fun}
	# compare the expected url with the received url.  if they match
	# the compare string will be empty or contain just the trailing
	# part of the url
	local _cmp=${_rcvd_url##$_exp_url}
	if [ "$_cmp" == "$_rcvd_url" ]; then
		# the expected url didn't match at all with the received url
		log_debug "rcvd: ${_rcvd_url} expd: ${_exp_url} cmp: ${_cmp}"
		return 1
	fi
	return 0
}

#DESC: check to see if nonce exists and has not expired
#RETURN: if exists remove and return 0, else return 1
#NOTE: see 6.5 and 6.5.1 and 7.2
check_nonce() {
	local _nt=0
	local _ct=`${DATE} +"%s"`
	local _rc=1
	local nonce=`query_req_field '.protected | .nonce'`
	if [ -z "${nonce}" ]; then
		return $_rc
	fi
	if [ -f ${ACME_DIR}/nonce/${nonce} ]; then
		_nt=`${CAT} ${ACME_DIR}/nonce/${nonce}`
		if [ ! -z "${_nt}" ]; then
			if [ $((${_nt} + ${NONCE_EXPIRE})) -gt ${_ct} ]; then
				_rc=0
			fi
		fi
		# remove old nonce
		${RM} -f ${ACME_DIR}/nonce/${nonce}
	fi	
	return $_rc
}

#DESC: create a new nonoce, record it, and return header with it
#RETURN: 0 if created, 1 if failed
make_nonce() {
	local _n
	local _f=5
	# loop MAX of 5 time... if we don't have a nonce by then, something is wrong
	while [ $_f -ne 0 ]; do
		_n=$(${OSSL} rand -hex 32)
		if [ ! -f ${ACME_DIR}/nonce/${_n} ]; then
			${DATE} +"%s" >${ACME_DIR}/nonce/${_n}
			set_header "Replay-Nonce: ${_n}"
			return 0
		fi
		_f=$(($_f-1))
	done
	log "ERROR" "make_nonce: failed to create nonce"
	return 1
}

verify_acct() {
	local acct
	local status
	acct=`query_req_field '.protected | .kid // ""'`
	if [ -z "${acct}" ]; then
		acct=`jwk_to_acct`
		if [ -z "${acct}" ]; then
			log "ERROR" "verify_acct: no kid or jwk found in request"
			echo "malformed" "no kid or jwk found in request"
			return 1
		fi
	else
		acct=`extract_id "${acct}"`
#		acct=${acct##*/acct/}
#		echo "${acct}" | grep -qE '^[a-zA-Z0-9_-]+$'
#		if [ $? -ne 0 ]; then
#			log_debug "verify_acct: error id: '$_r'"
#			echo "malformed" "invalid id"
#			return 1
#		fi
	fi
	log_debug "verify_acct: cound account ${acct}"
	if [ ! -f ${ACME_DIR}/accts/${acct} ]; then
		log "ERROR" "verify_acct: Account ${acct} does not exist."
		echo "accountDoesNotExist" "cannot find existing account"
		return 1
	else
		# check the account status
		status=`query_account_field ${acct} '.status // ""'`
		if [ $? -ne 0 ]; then
			log "ERROR" "verify_acct: missing account status"
			echo "serverInternal" "missing account info"
			return 1
		fi
		log_debug "verify_acct: account status ${status}"
		if [ "${status}" != "valid" ]; then
			log "ERROR" "verify_acct: account ${acct} is ${status}"
			echo "accountNotValid" "account ${acct} is ${status}"
			return 1
		fi
	fi
	echo "${acct}"
	return 0
}

#DESC: return the directory json to the client
#NOTE: look into updating meta.caaIdentities with array of 'allowed' domains
#NOTE: look into updating meta.termsOfService with link to a TOS document
#NOTE: this does not support newAuthz command
handle_directory() {
	set_header "Content-Type: application/json"
	_BODY='{
  "meta": {
	"externalAccountRequired": false
  },
  "newNonce": "'${ISSUER_URL}'/nonce",
  "newAccount": "'${ISSUER_URL}'/acct",
  "newOrder": "'${ISSUER_URL}'/order",
  "newAuthz": "'${ISSUER_URL}'/authz",
  "revokeCert": "'${ISSUER_URL}'/revoke",
  "keyChange": "'${ISSUER_URL}'/keychange"
}'
#  "renewalInfo": "'${ISSUER_URL}'/renewal-info"
	return_result 200 "OK"
	#no return
}

#DESC: create a new nonce and return it
handle_new_nonce() {
	make_nonce || return_error 500 "badNonce" "failed to create new nonce"
	_BODY=""
	if [ "$REQUEST_METHOD" == "HEAD" ]; then
		return_result 200 "OK"
	else	# assume GET
		return_result 204 "No Content"
	fi
	# no return
}

#DESC: process account requests (add, update, deactivation)
handle_account() {
	local acct
	local ore
	local contacts
	make_nonce || return_error 500 "badNonce" "failed to create new nonce"
	# check for account without a trailing slash "/".  if true, this is a new request
	acct=${REQUEST_URI##*/acct}	
	if [ -z "${acct}" ]; then
		# no account info sent
		log_debug "handle_account: new account request"
		# new account request
		acct=`jwk_to_acct`
		if [ ! -f ${ACME_DIR}/accts/${acct} ]; then
			ore=`query_req_field '.payload | .onlyReturnExisting // ""'`
			if [ ! -z "${ore}" -a "${ore}" == "true" ]; then
				log_debug "handle_account: ignore new account creation per client request"
				log "INFO" "Account lookup for ${acct} requested.  Does not exist."
				return_error 200 "accountDoesNotExist" "account creation ignored at client request"
			fi
			# check contacts
			contacts=`query_req_field '.payload | .contact[] // ""'`
			if [ -z "${contacts}" ]; then
				log_debug "handle_account: no contacts specified"
				log "ERROR" "No contacts specified for new account ${acct}"
				return_error 424 "invalidContact" "no contact informaton supplied"
				# no return
			fi
			log_debug "handle_account: creating new account"
			_BODY='{ "status": "valid", "orders": "'${ISSUER_URL}'/orders/'${acct}'", "termsOfServiceAgreed": "'$(query_req_field '.payload | .termsOfServiceAgreed')'", "contact": '$(query_req_field '.payload | .contact')', "jwk": '$(query_req_field '.protected | .jwk')' }'
			echo "$_BODY" > ${ACME_DIR}/accts/${acct}
			if [ $? -ne 0 ]; then
				log_debug "handle_account: failed to save account"
				log "ERROR" "failed to save account ${acct}"
				return_error 500 "serverInternal" "failed to save account"
				# return
			fi
			_BODY=$(${CAT} ${ACME_DIR}/accts/${acct})
			set_header "Location: ${ISSUER_URL}/acct/${acct}"
			log "INFO" "Account ${acct} created"
			return_result 201 "Created"
			# no return
		else
			# account already exists
			log_debug "handle_account: account already exists"
			log "INFO" "Account ${acct} already exists."
			set_header "Location: ${ISSUER_URL}/acct/${acct}"
			_BODY=$(${CAT} ${ACME_DIR}/accts/${acct})
			return_result 200 "Ok"
			# no return
		fi
	else
		# existing account request
		log_debug "handle_account: account update request"
		acct=`verify_acct` || return_error 400 ${acct}
		log_debug "handle_account: account ${acct}"
		# check the account status
		local status
		status=`query_account_field ${acct} '.status'` || return_error 404 "serverInternal" "missing account info"
		log_debug "handle_account: account status ${status}"
		case "${status}" in
			deactivated)
				return_error 400 "unauthorized" "account ${acct} is ${status}"
				# no return
				;;
			valid)
				# just fall thru
				;;
			*)
				return_error 404 "accountNotValid" "account ${acct} is ${status}"
				# no return
				;;
		esac
		# update account info...
		status=`query_req_field '.payload | .status //""'`
		if [ ! -z "${status}" ]; then
			if [ "${status}" != "deactivated" ]; then
				# only permit client to deactivate account
				return_error 400 "unauthorized" "invalid request to set status to ${status}"
				# no return
			fi
			log_debug "handle_account: set account status to ${status}"
			set_account_field "${acct}" '.status = "'${status}'"' || return_error 404 "serverInternal" "error updating account status"
		else
			local new_contact=`query_req_field '.payload | .contact // ""'`
			log_debug "handle_account: set account contact to ${new_contact}"
			if [ ! -z "${new_contact}" ]; then
				set_account_field "${acct}" '.contact = "'${new_contact}'"' || return_error 404 "serverInternal" "error updating account contact"
			fi
		fi
		_BODY=$(${CAT} ${ACME_DIR}/accts/${acct})
		log_debug "handle_account: account updated"
		set_header "Location: ${ISSUER_URL}/acct/${acct}"
		log "INFO" "Account ${acct} updated."
		return_result 200 "OK"
		# no return
	fi
	return_error 400 "serverInternal" "internal error when processing account"
	# no return
}

# DESC: return a list of orders for a specified account
handle_orders() {
	local acct
	local status
	local olist
	make_nonce || return_error 400 "badNonce" "failed to create new nonce"
	# abusing the acct response
	acct=`verify_acct` || return_error 400 ${acct}
	olist=`${LS} -1r ${ACME_DIR}/orders/${acct}_* | ${JQ} -Rs '. | split("\n") | map(select (. != "")) | map("'${ISSUER_URL}'/order" + .) | { orders: .}'`
	log_debug "handle_orders: orders ${olist}"
	_BODY=${olist}
	return_result 200 "OK"
	# no return
}

handle_key_change() {
	log_debug "handle_key_change: return 405"
	return_result 405 "Method Not Allowed"
}

handle_order() {
	local acct
	local status
	make_nonce || return_error 400 "badNonce" "failed to create new nonce"
	# abusing the acct response
	acct=`verify_acct` || return_error 400 ${acct}
	local raw_identifiers=`query_req_field '.payload | .identifiers'`
	local identifiers=`query_req_field '.payload | .identifiers[] | "\(.type):\(.value)"'`
	local notBefore=`query_req_field '.payload | .noBefore // ""'`
	local notAfter=`query_req_field '.payload | .noBefore // ""'`
	local now=`get_epoch`
	local max=$((${now}+${MAX_CERT_TIME}))
#	log_debug "handle_order: identifiers=${raw_identifiers}"
#	log_debug "handle_order: identifiers=${identifiers}"
	if [ ! -z ${notBefore} ]; then
		local nb=`rfc3339_to_epoch "${notBefore}"`
		if [ ${nb} -gt ${now} ]; then
			# notBefore is in the future
			return_result 400 "Bad Request"
		fi
	fi
	if [ ! -z ${notAfter} ]; then
		local na=`rfc3339_to_epoch "${notAfter}"`
		if [ ${na} -gt ${max} ]; then
			# notAfter is longer than MAX_CERT_TIME
			return_result 400 "Bad Request"
		fi
	fi
	# verify we can handle the authz
	for _id in ${identifiers}; do
		local t=`echo "${_id}" | ${CUT} -f1 -d:`
		case $t in
			dns) ;;
			*)
			return_error 404 "unsupportedIdentifier" "do not support ${t} identifiers"
			# no return
			;;
		esac
	done
	local order=`${OSSL} rand -hex 8`
	local authorizations
	local expire
#XXX create an authorization for each identifier
	authorizations="[ \"${ISSUER_URL}/authz/${acct}_${order}\" ]"
	expire=`epoch_to_rfc3339 $((${now}+${ORDER_EXPIRE}))`
	notBefore=`epoch_to_rfc3339 ${now}`
	notAfter=`epoch_to_rfc3339 ${max}`
	make_nonce
	set_header "Location: ${ISSUER_URL}/order/${order}"
	_BODY='{
  "status": "pending",
  "expires": "'${expire}'",
  "notBefore": "'${notBefore}'",
  "notAfter": "'${notAfter}'",
  "identifiers": '${raw_identifiers}',
  "authorizations" : '${authorizations}',
  "finalize": "'${ISSUER_URL}'/finalize/'${acct}'_'${order}'"
}'
	echo "${_BODY}" > ${ACME_DIR}/orders/${acct}_${order}
	if [ $? -ne 0 ]; then
		_BODY=""
		return_result 500 "error saving order"
		#no return
	fi
	# return success to requestor
	return_result 201 "Created"
	# no return
}

handle_authz() {
	local acct
	local status
	make_nonce || return_error 400 "badNonce" "failed to create new nonce"
	# abusing the acct response
	acct=`verify_acct` || return_error 400 ${acct}
#XXX handle 'deactivate' requests
	local order=`extract_id`
	if [ -z "$order" ]; then
		log "ERROR" "authz: no order specified"
		return_error 400 "malformed" "no order in url"
		# no return
	fi
	log_debug "handle_authz: order ${order}"
	if [ -f ${ACME_DIR}/challenges/${order} ]; then
		log_debug "handle_authz: processing chanllenge ${order}"
		# just load the file for return.  The status will be updated by the testing functions
		_BODY=$(${CAT} ${ACME_DIR}/challenges/${order})
		status=`query_challenge_field "$order" '.status // ""'`
		case "${status}" in
			"valid")
				set_order_field "${order}" '.status = "valid"'
				if [ $? -ne 0 ]; then
					log "ERROR" "could not set order state to valid for order ${order}"
					return_error 501 "serverInternal" "error seting order state to valid"
					# no return
				fi
				;;
			"invalid")
				set_order_field "${order}" '.status = "invalid"'
					log "ERROR" "could not set order state to invalid for order ${order}"
					return_error 501 "serverInternal" "error seting order state to invalid"
					# no return
				;;
		esac
	else
		log_debug "handle_authz: creating new challenge"
		local token=`${OSSL} rand -hex 16`
		local identifiers=`query_order_field "${order}" ".identifiers"` || return_error 500 "serverInternal" "cannt retrieve identifires from order"
		local expires=`query_order_field "${order}" ".expires"` || return_error 500 "serverInternal" "cannot retrieve expire from order"
		local challenges='[
{ "type": "http-01", "url": "'${ISSUER_URL}'/challenge/'${order}'", "status": "pending", "token": "'${token}'" }
]'
#{ "type": "dns-01", "url": "'${ISSUER_URL}'/challenge/'${order}'", "status": "pending", "token": "'${token}'" },
		_BODY='{ "status": "pending", "expires": "'${expires}'", "identifier": '${identifiers}', "challenges": '${challenges}' }'
		# save challenge document
		echo "$_BODY" > ${ACME_DIR}/challenges/${order}
		if [ $? -ne 0 ]; then
			return_error 500 "serverInternal" "error saving challenge object"
			# no return
		fi
	fi
	return_result 200 "OK"
	# no return
}

handle_challenge() {
	local acct
	local status
	make_nonce || return_error 400 "badNonce" "failed to create new nonce"
	# abusing the acct response
	acct=`verify_acct` || return_error 400 ${acct}
	local order=`extract_id`
	if [ -z "$order" ]; then
		log "ERROR" "challenge: no order specified"
		return_error 400 "malformed" "no order in url"
		# no return
	fi
	log_debug "handle_challenge: order ${order}"
	if [ -f ${ACME_DIR}/challenges/${order} ]; then
		status=`query_challenge_field ${order} '.status // ""'` || return_error 500 "serverInternal" "cannot find status"
		log_debug "handle_challenge: challenge status ${status}"
		case "${status}" in
			"pending")
				set_header "Retry-After: ${CLIENT_RETRY}"
				_BODY=`query_challenge_field ${order} '.challenges // ""'` || return_error 500 "serverInternal" "error parsing challenges"
				if [ -z "${_BODY}" ]; then
					# no challenges found...
					return_error 400 "malformed" "no valid challenges found"
					# no return
				fi
				# call ourselves to process the order
				$0 -x ${order}
				;;
			"processing")
				# still trying
				set_header "Retry-After: ${CLIENT_RETRY}"
				return_result "204" "No Content"
				# no return
				;;
			"valid")
				# done... return first challenge object that has status of 'valid'
				_BODY=`query_challenge_field ${order} '.challenges | map(select(.status == "valid")) | .[0] // ""'` || return_error 500 "serverInternal" "error parsing challenges"
				if [ -z "${_BODY}" ]; then
					# no challenges found...
					return_error 400 "malformed" "no valid challenges found"
					# no return
				fi
#log_debug "handle_challenge: resp: ${_BODY}"
				return_result 200 "OK"
				# no return
				;;
			"invalid")
				_BODY=`query_challenge_field ${order} '.challenges | map(select(.status == "invalid")) | .[0] // ""'` || return_error 500 "serverInternal" "error parsing challenges"
				if [ -z "${_BODY}" ]; then
					# no challenges found...
					return_error 400 "malformed" "no valid challenges found"
					# no return
				fi
				return_result 200 "OK"
				# no return
				;;
			*)
				return_error 500 "serverInternal" "invalid challenge state: $status"
				# no return
				;;
		esac
	else
		return_error 401 "invalidChallenge" "cannot find requested challenge"
		# no return
	fi
	return_result 200 "OK"
	# no return
}

handle_finalize() {
	local acct
	local status
	local _csr
	local _ret
	make_nonce || return_error 400 "badNonce" "failed to create new nonce"
	# abusing the acct response
	acct=`verify_acct` || return_error 400 ${acct}
	local order=`extract_id`
	if [ -z "$order" ]; then
		log "ERROR" "finalize: no order specified"
		return_error 400 "malformed" "no order in url"
		# no return
	fi
	log_debug "handle_finalize: order ${order}"
	if [ -f ${ACME_DIR}/orders/${order} ]; then
		status=`query_order_field ${order} '.status // ""'` || return_error 500 "serverInternal" "cannot find order status"
		log_debug "handle_finalize: order status ${status}"
		case "${status}" in
			"valid")
				_csr=`query_req_field '.payload | .csr // ""'` || return_error 500 "serverInternal" "error extracting the CSR"
				if [ -z "${_csr}" ]; then
					return_error 499 "malformed" "CSR not found in request"
					# no return
				fi
				echo "-----BEGIN CERTIFICATE REQUEST-----\n$(url_unprotect ${_csr})\n-----END CERTIFICATE REQUEST-----" > ${ACME_DIR}/certs/${order}.req
				if [ $? -ne 0 ]; then
					return_error 500 "serverInternal" "error saving csr"
					# no return
				fi
				_ret=`process_csr ${order}`
				if [ $? -ne 0 ]; then
					return_error 400 "badCSR" "${_ret}"
					# no return
				fi
				set_order_field "${order}" '.certificate = "'${ISSUER_URL}'/certificate/'${order}'"'
				if [ $? -ne 0 ]; then
					log "ERROR" "could not set certificate link on order ${order}"
					return_error 501 "serverInternal" "error seting certificate for order"
					# no return
				fi
				_BODY=$(${CAT} ${ACME_DIR}/orders/${order})
				# drop thru and return OK
				;;
			"ready")
				return_error 499 "orderNotReady" "order not ready to be finalized"
				# no return
				;;
			"pending")
				return_error 499 "orderNotReady" "order not ready to be finalized"
				# no return
				;;
			"processing")
				return_error 499 "orderNotReady" "order not ready to be finalized"
				# no return
				;;
			"invalid")
				return_error 499 "orderNotReady" "order not ready to be finalized"
				# no return
				;;
			*)
				return_error 500 "serverInternal" "invalid order state: $status"
				# no return
				;;
		esac
	else
		return_error 401 "invalidChallenge" "cannot find requested order"
		# no return
	fi
	return_result 200 "OK"
	# no return
}

handle_certificate() {
	local acct
	local status
	make_nonce || return_error 400 "badNonce" "failed to create new nonce"
	# abusing the acct response
	acct=`verify_acct` || return_error 400 ${acct}
	local order=`extract_id`
	if [ -z "$order" ]; then
		log "ERROR" "certificate: no order specified"
		return_error 400 "malformed" "no order in url"
		# no return
	fi
	log_debug "handle_certificate: order ${order}"
	if [ -f ${ACME_DIR}/certs/${order}.pem ]; then
#NOTE: CAT to _BODY eats the newline and borks the cert. so replicate the
# return_success() function.
		set_header "Content-Type: application/pem-certificate-chain"
		set_header "Link: <${ISSUER_URL}/directory>;rel=\"index\""
		# return the HTTP status back to CGI interperter
		echo "Status: 200 $(hc_string ${_hc})"
		# output the headers
		for _h in "${_HEADERS[@]}"; do
			echo "${_h}"
		done
		echo
		# output a body if it exists
		${CAT} ${ACME_DIR}/certs/${order}.pem | ${SED} -n '/^-----/,/^-----/p'
		clean_content
		exit 0
	else
		return_error 401 "invalidChallenge" "cannot find requested order"
		# no return
	fi
	return_result 200 "OK"
	# no return
}

handle_revoke() {
	local acct
	local status
	make_nonce || return_error 400 "badNonce" "failed to create new nonce"
	acct=`verify_acct` || return_error 400 ${acct}
	_ret=`process_revoke ${acct}`
	case "$?" in
		1) #alreadyRevoked
			return_error 401 "alreadyRevoked" "${_ret}"
			# no return
			;;
		2) #not found
			return_error 401 "badCertificate" "${_ret}"
			# no return
			;;
		3) # other
			return_error 401 "malformed" "${_ret}"
			# no return
			;;
	esac

	_BODY=""
	return_result 200 "OK"
	# no return
}

### --- MAIN ---
conf=`find_conf`
if [ -z "${conf}" ]; then
	echo "Status: 500 config not found"
	exit 1
else
	. ${conf}
fi

# --- CONFIG ---
# no defaults
ISSUER_DOMAIN=${ISSUER_DOMAIN:-""}
ISSUER_EMAIL=${ISSUER_EMAIL:-""}
ISSUER_URL=${ISSUER_URL:-"https://${ISSUER_DOMAIN}/acme"}
# has defaults
LOG_FILE=${LOG_FILE:-"/logs/acme.log"}
ACME_DIR=${ACME_DIR:-"/acme"}
NONCE_EXPIRE=${NOCE_EXPIRE:-300}
MAX_CERT_DAYS=${MAX_CERT_DAYS:-90}
MAX_CERT_TIME=$((90*86400))
CLIENT_RETRY=${CLIENT_RETRY:-5}
ORDER_EXPIRE=${ORDER_EXPIRE:-300}
VERIFY_TIMEOUT=${VERIFY_TIMEOUT:-1}
VERIFY_RETRIES=${VERIFY_RETIRES:-1}
VERIFY_DELAY=${VERIFY_DELAY:-1}
CA_HELPER=${CA_HELPER:-"/cgi-bin/ACME_helper.sh"}
DEBUG=${DEBUG:-0}
DEVNUL=${DEVNUL:-"/tmp/acme-stderr.out"}

if [ -z "${ISSUER_DOMAIN}" -o -z "${ISSUER_EMAIL}" ]; then
	echo "Status: 500 incomplete config"
	exit 1
fi

# If HTTP_HOST is set, build the URL from it as it will
# handle any name:port.  This allows for loadbalancing
# and hosting on different port than 443
if [ ! -z "${HTTP_HOST}" ]; then
	ISSUER_URL="https://${HTTP_HOST}/acme"
fi

# send all stderr to DEVNUL file
exec 2>${DEVNUL}

# disable globing
set -o noglob

# if we are called with -x ordernumber, close all stdin,stdout,stderr and background ourselves
if [ $# -gt 1 -a "$1" == "-x" ]; then
	( cd /; 0<&-; 1>&-; 2>&-; process_challenge "$2") &
	exit 0
fi

# prevent caching of responses
set_header "Cache-Control: public, max-age=0, no-cache"
#SEE 6.1
set_header 'Access-Control-Allow-Origin: *'

# create dir structure (if not exists)
check_dirs ${ACME_DIR}
if [ $? -ne 0 ]; then
	log_debug "one or more directories missing in ${ACME_DIR}"
	return_error 503 "serverInternal" "server failed internal checks"
	# no return
fi

## request must use HTTPS
if [ -z "$HTTPS" -o "$HTTPS" != "on" ]; then
	log_debug "HTTPS not used: '$HTTPS'"
	return_error 400 "malformed" "HTTPS must be used"
	# no return
fi
if [ -z "$HTTP_USER_AGENT" ]; then
	log "ERROR" "User agent not specified"
	# rfc 8555 6.1 states that useragent MUST be sent
	return_error 400 "malformed" "User-Agent not specified"
	# no return
fi

# read the content into temporary file for later handling
read_content

# --- MAIN CGI HANDLER ---
log_debug "request uri: $DOCUMENT_URI"
case "$DOCUMENT_URI" in
	*"/directory")
		handle_directory
		# no return
		;;
	*"/nonce") # Get New Nonce
		handle_new_nonce
		# no return
		;;
	*"/acct"*)
		check_post_as_get || return_error 400 "malformed" "request expected POST-as-GET"
		check_url "acct" || return_error 400 "malformed" "url doesn't match request"
		check_nonce || return_error 400 "badNonce" "Nonce could not be found or had expired"
		validate_jws || return_error 400 "badPublicKey" "JWS could not be verified"
        handle_account 
		# no return
		;;
	*"/orders"*)
		check_post_as_get || return_error 400 "malformed" "request expected POST-as-GET"
		check_url "orders" || return_error 400 "malformed" "url doesn't match request"
		check_nonce || return_error 400 "badNonce" "Nonce could not be found or had expired"
		validate_jws || return_error 400 "badPublicKey" "JWS could not be verified"
        handle_account 
		# no return
		;;
    *"/order"*)
		check_post_as_get || return_error 400 "malformed" "request expected POST-as-GET"
		check_url "order" || return_error 400 "malformed" "url doesn't match request"
		check_nonce || return_error 400 "badNonce" "Nonce could not be found or had expired"
		validate_jws || return_error 400 "badPublicKey" "JWS could not be verified"
        handle_order
		# no return
        ;;
    *"/authz"*)
		check_post_as_get || return_error 400 "malformed" "request expected POST-as-GET"
		check_url "authz" || return_error 400 "malformed" "url doesn't match request"
		check_nonce || return_error 400 "badNonce" "Nonce could not be found or had expired"
		validate_jws || return_error 400 "badPublicKey" "JWS could not be verified"
        handle_authz
		# no return
        ;;
	*"/challenge"*)
		check_post_as_get || return_error 400 "malformed" "request expected POST-as-GET"
		check_url "challenge" || return_error 400 "malformed" "url doesn't match request"
		check_nonce || return_error 400 "badNonce" "Nonce could not be found or had expired"
		validate_jws || return_error 400 "badPublicKey" "JWS could not be verified"
        handle_challenge
        ;;
	*"/finalize"*)
		check_post_as_get || return_error 400 "malformed" "request expected POST-as-GET"
		check_url "finalize" || return_error 400 "malformed" "url doesn't match request"
		check_nonce || return_error 400 "badNonce" "Nonce could not be found or had expired"
		validate_jws || return_error 400 "badPublicKey" "JWS could not be verified"
        handle_finalize
        ;;
	*"/certificate"*)
		check_post_as_get || return_error 400 "malformed" "request expected POST-as-GET"
		check_url "certificate" || return_error 400 "malformed" "url doesn't match request"
		check_nonce || return_error 400 "badNonce" "Nonce could not be found or had expired"
		validate_jws || return_error 400 "badPublicKey" "JWS could not be verified"
        handle_certificate
        ;;
	*"/revoke"*)
		check_post_as_get || return_error 400 "malformed" "request expected POST-as-GET"
		check_url "revoke" || return_error 400 "malformed" "url doesn't match request"
		check_nonce || return_error 400 "badNonce" "Nonce could not be found or had expired"
		validate_jws || return_error 400 "badPublicKey" "JWS could not be verified"
		handle_revoke
        ;;
	*"/keychange"*)
		check_post_as_get || return_error 400 "malformed" "request expected POST-as-GET"
		check_url "key-change" || return_error 400 "malformed" "url doesn't match request"
		check_nonce || return_error 400 "badNonce" "Nonce could not be found or had expired"
		validate_jws || return_error 400 "badPublicKey" "JWS could not be verified"
        handle_key_change 
		# no return
		;;
	*)
		set_header "Content-Type: text/plain"
		_BODY="unknown API $DOCUMENT_URI"
		return_result 521 "unknown API"
		;;
esac
exit 0


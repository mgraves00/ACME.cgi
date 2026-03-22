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
	local _sev _d _h
	_sev=$1; shift;
	_d=$(now_epoch)
	_h=${HTTP_X_FORWARDED_FOR:-${REMOTE_ADDR:-"unknown"}}
    echo "$(epoch_to_rfc3339 "${_d}") [${_sev}] ${_h} $*" >>"$LOG_FILE"
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
		accountDoesNotExist)	echo 400;;
		alreadyRevoked)			echo 400;;
		badCSR)					echo 400;;
		badNonce)				echo 400;;
		badPublicKey)			echo 400;;
		badRevocationReason)	echo 406;;
		badSignatureAlgorithm)	echo 406;;
		caa)					echo 400;;
		compound)				echo 400;;
		connection)				echo 400;;
		conflict)				echo 409;;
		dns)					echo 400;;
		externalAccountRequired)echo 400;;
		incorrectResponse)		echo 400;;
		invalidContact)			echo 424;;
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

uc() {
	if [ $# -eq 0 ]; then
		${CAT} | ${TR} 'a-z' 'A-Z'
	else
		echo "$*" | ${TR} 'a-z' 'A-Z'
	fi
}
lc() {
	if [ $# -eq 0 ]; then
		${CAT} | ${TR} 'A-Z' 'a-z'
	else
		echo "$*" | ${TR} 'A-Z' 'a-z'
	fi
}

clean_content() {
	if [ -n "${_REQ_FILE}" -a -f "${_REQ_FILE}" ]; then
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
			_e=$(${DATE} +"%s" -d "$1")
			;;
		*)
			_e=$(${DATE} -j -f "%Y-%m-%dT%H:%M:%S%z" +"%s" "$1")
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
			_e=$(${DATE} +"%Y-%m-%dT%H:%M:%SZ" -d "@$1")
			;;
		*)
			_o=$(${DATE} -j -r "$1" +"%Y-%m-%dT%H:%M:%SZ")
#			_o=$(${DATE} -j -r "$1" +"%Y-%m-%dT%H:%M:%S%z")
			;;
	esac
	echo "${_o}"
}

now_epoch() {
	local _e
	case $(${UNAME}) in
		Linux)
			_e=$(${DATE} +"%s")
			;;
		*)
			_e=$(${DATE} -j +"%s")
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
	while [ "${#hex}" -gt 2 ] && [ "$(echo -n "${hex}" | ${CUT} -c1-2)" == "00" ]; do
		hex=$(echo -n "${hex}" | cut -c3-)
	done
	# if high bit set, prepend 00 so integer stays positive
	[ $(( 0x$(echo -n "$hex" | ${CUT} -c1-2) )) -ge 128 ] && hex="00${hex}"
    len=$(( ${#hex} / 2 ))
    ${PRINTF} "02%s%s" "$(_der_len "$len")" "$hex"
}
_der_bitstring() {
    local inner="00$1"; local len=$(( ${#inner} / 2 ))
    ${PRINTF} "03%s%s" "$(_der_len "$len")" "$inner"
}
_der_octetstring() {
    local len
	len=$(( ${#1} / 2 ))
    ${PRINTF} "04%s%s" "$(_der_len "$len")" "$1"
}
_der_oid() {
    local len
	len=$(( ${#1} / 2 ))
    ${PRINTF} "06%s%s" "$(_der_len "$len")" "$1"
}
_der_ctx0() {
    local len
	len=$(( ${#1} / 2 ))
    ${PRINTF} "a0%s%s" "$(_der_len "$len")" "$1"
}
_der_ctx1() {
    local len
	len=$(( ${#1} / 2 ))
    ${PRINTF} "a1%s%s" "$(_der_len "$len")" "$1"
}
_hex_pad() {
    local hex target
	hex=$1 target=$(( $2 * 2 ))
    while [ "${#hex}" -lt "$target" ]; do hex="00${hex}"; done
    ${PRINTF} "%s" "$hex"
}
# variables cannot store null bytes. this means we can only pass the data thru
_bin_to_hex() {
#	local _s
#	_s=$@
#	if [ ${#_s} -eq 0 ]; then
#		_s=$(${CAT})
#	fi
#	echo -n "${_s}" | ${OD} -A n -v -t x1 | ${TR} -d '\r\t\n '
	${OD} -A n -v -t x1 | ${TR} -d '\r\t\n '
}
#NOTE: outputs binary stream
_hex_to_bin() {
	local _s _h
	_s=$*
	if [ ${#_s} -eq 0 ]; then
		_s=$(${CAT})
	fi
	for _h in $(echo -n "${_s}" | ${SED} 's/\([0-9a-fA-F]\{2\}\)/ \1/g'); do
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
	local h1 h2 _s _b _sz
	_s=$1; shift
	_b=${1:-ES256}
	_sz=0
	if [ -z "${_s}" ]; then
		log_debug "s2d: unable to read string"
		return 1
	fi
	_s=$(echo -n "$_s" | url_unprotect | ${OSSL} enc -a -A -d | _bin_to_hex)
	case "${_b}" in
		ES256)
			if [ "${#_s}" -ne 128 ]; then
				log_debug "invalid signature size 128 != ${#_s}"
				return 1
			fi
			_sz=64
			;;
		ES384)
			if [ "${#_s}" -ne 192 ]; then
				log_debug "invalid signature size 192 != ${#_s}"
				return 1
			fi
			_sz=96
			;;
		ES521)
			if [ "${#_s}" -ne 264 ]; then
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
	if [ "${_sz}" -eq 0 ]; then
		log_debug "s2b size not set"
		return 1
	fi
	case "${_b}" in
		ES*)
			h1=$(echo -n "${_s}" | ${CUT} -c1-${_sz})
			h2=$(echo -n "${_s}" | ${CUT} -c$((_sz+1))-)
			_s=$(_der_seq "$(_der_int "${h1}")$(_der_int "${h2}")")
			;;
		RS*)
			# just output signature
			;;
	esac
	# now output signature in DER format
	echo -n "${_s}" | _hex_to_bin
}

extract_id() {
	local _id _r _cmp
	_id=${1:-${REQUEST_URI}}
	_r=${_id##*/}
	_cmp=$(echo -n "$_r" | ${SED} -nr '/^[a-zA-Z0-9_-]+$/p')
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
	if [ -n "${CONTENT_LENGTH}" ]; then
		if [ "${CONTENT_LENGTH}" -gt "${MAX_REQUEST_SIZE}" ]; then
			log "ERROR" "content size exceeded max size: ${CONTENT_LENGTH} too large"
			return_error 413 "malformed" "request too large"
			# no return
		fi
		_REQ_FILE=$(${MKTEMP} -t "acme-XXXXXX.json")
		if [ $? -ne 0 ]; then
			log "ERROR" "read_content: error createing tmp file"
			return_error 500 "serverInternal" "error creating tmp file"
			# no return
		fi
		log_debug "read_content: _REQ_FILE=${_REQ_FILE}"
		# NOTE: relying on http server to actually limit the max size of the request
		${CAT} - >"${_REQ_FILE}"
		_sz=$(${CAT} "${_REQ_FILE}" | ${WC} -c | ${TR} -d ' ')
		if [ "${CONTENT_LENGTH}" -ne "${_sz}" ]; then
			log "ERROR" "read_content: content_length: ${CONTENT_LENGTH} != content_size: ${_sz}"
			return_error 413 "malformed" "Content Size Mismatch"
			# no return
		fi
		log_debug "read_content: content size ${_sz}"
		# save the protect and payload in base64 for validating jwk
		_JWK64=$(${CAT} "${_REQ_FILE}" | ${JQ} -cr '(.protected // "") + "." + (.payload // "")')
		# decode the base64 encodings
		_encstr=$(${CAT} "${_REQ_FILE}" | ${JQ} -r '.protected = (.protected | @base64d | fromjson) | .payload = try (.payload | @base64d | fromjson) catch ""')
		if [ $? -ne 0 ]; then
			log "ERROR" "read_content: error decoding content"
			return_error  413 "malformed" "error decoding b64"
			# no return
		fi
		echo "${_encstr}" >"${_REQ_FILE}"
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
	local _s _l
	if [ $# -eq 0 ]; then
		_s=$(${CAT})
	else
		_s=$*
	fi
	_l=$((${#_s} % 4))
	if [ $_l -eq 2 ]; then
		_s="${_s}=="
	elif [ $_l -eq 3 ]; then
		_s="${_s}="
	fi
	echo -n "${_s}" | ${TR} '_-' '/+'
}

#NOTE: investigate a file locking scheme
set_file_field() {
	local _file _f _res
	_file=$1
	_f=$2
	if [ -z "${_file}" ]; then
		log_debug "set_file_filed: no file given"
		return 1
	fi
	if [ ! -f "${_file}" ]; then
		log_debug "set_file_field: no file ${_file}"
		return 1
	fi
	_res=$(${CAT} "${_file}" | ${JQ} -cr "${_f}")
	if [ $? -ne 0 ]; then
		log_debug "set_file_field: error setting field ${_f} from ${_file}"
		return 1
	fi
	echo "${_res}" >"${_file}"
	if [ $? -ne 0 ]; then
		log_debug "set_file_field: error saving file ${_file}"
	fi
	return 0
}

query_file_field() {
	local _file _f _res
	_file=$1;
	_f=$2;
	if [ -z "${_file}" ]; then
		log_debug "query_file_field: no file given"
		echo ""
		return 1
	fi
	if [ ! -s "${_file}" ]; then
		log_debug "query_file_field: no file or size is 0: ${_file}"
		echo ""
		return 1
	fi
	_res=$(${CAT} "${_file}" | ${JQ} -cr "${_f}")
	if [ $? -ne 0 ]; then
		log_debug "query_file_field: error fetching field '${_f}' from ${_file}"
#cat ${_file} >&2
		echo ""
		return 1
	fi
	echo "${_res}"
	return 0
}

query_req_field() {
	local _f _rc _res
	_f=$1
	_res=$(query_file_field "${_REQ_FILE}" "${_f}")
	if [ $? -ne 0 ]; then
		return 1
	fi
	echo "${_res}"
	return 0
}

query_account_field() {
	local _n _f _rc _res
	_n=$1
	_f=$2
	_res=$(query_file_field "${ACME_DIR}/accts/${_n}" "${_f}")
	if [ $? -ne 0 ]; then
		return 1
	fi
	echo "${_res}"
	return 0
}

query_order_field() {
	local _n _f _rc _res
	_n=$1
	_f=$2
	_res=$(query_file_field "${ACME_DIR}/orders/${_n}" "${_f}")
	if [ $? -ne 0 ]; then
		return 1
	fi
	echo "${_res}"
	return 0
}

query_challenge_field() {
	local _n _f _rc _res
	_n=$1
	_f=$2
	_res=$(query_file_field "${ACME_DIR}/challenges/${_n}" "${_f}")
	if [ $? -ne 0 ]; then
		return 1
	fi
	echo "${_res}"
	return 0
}

set_account_field() {
	local _n _f _rc _res
	_n=$1
	_f=$2
	_res=$(set_file_field "${ACME_DIR}/accts/${_n}" "${_f}")
	if [ $? -ne 0 ]; then
		return 1
	fi
	return 0
}

set_order_field() {
	local _n _f _rc _res
	_n=$1
	_f=$2
	_res=$(set_file_field "${ACME_DIR}/orders/${_n}" "${_f}")
	if [ $? -ne 0 ]; then
		return 1
	fi
	return 0
}

set_challenge_field() {
	local _n _f _rc _res
	_n=$1
	_f=$2
	_res=$(set_file_field "${ACME_DIR}/challenges/${_n}" "${_f}")
	if [ $? -ne 0 ]; then
		return 1
	fi
	return 0
}

#NOTE: return comma separated list
extract_san() {
	local _sans _reqfile _typ
	_reqfile=$1
	_typ=${2:-"x509"}
	if [ -z "${_reqfile}" -o ! -f "${_reqfile}" ]; then
		log_debug "extact_san: cannot find request file"
		return 1
	fi
	_sans=$(${OSSL} "${_typ}" -in "${_reqfile}" -noout -text | \
			${SED} -n '/Subject Alternative Name/,/Signature Algorithm/p' | \
			${SED} -e '/Subject Alternative Name/d' -e '/Signature Algorithm/d' | \
			${TR} -d "\t ")
	echo "${_sans}"
	return 0
}

verify_dns_name() {
	local _dns _t _p
	_dns=$1
	_dns=$(lc "${1}")
	# error on records with '*'
	_t=$(echo "${_dns}" | ${TR} -d '*')
	if [ "${_dns}" != "${_t}" ]; then
		log_debug "verify_dns_name: found wildcard SAN"
		return 1
	fi
	# check for invalid characters
	_t=$(echo -n "${_dns}" | ${TR} -d '[:print:]')
	if [ -n "${_t}" ]; then
		log_debug "verify_dns_name: found non-printable characters: ${_dns} <=> ${_t}"
		return 1
	fi
	# make sure that no portion of the domain is > 63 characters
	for _p in $(echo -n "${_dns}" | ${TR} '.' '\n'); do
		if [ "${#_p}" -gt 63 ]; then
			log_debug "verify_dns_name: name part >63 characters"
			return 1
		fi
		if [ "${#_p}" -eq 0 ]; then
			log_debug "verify_dns_name: name part 0 characters"
			return 1
		fi
	done
	# make sure dns length is < 254 characters
	if [ "${#_dns}" -ge 254 ]; then
		log_debug "verify_dns_name: SAN >253 characters"
		return 1
	fi
	# make sure it doesn't start or end with hyphen
	_t=$(echo "${_dns}" | ${SED} -n -E '/^[0-9a-z]([a-z0-9\.-]*[0-9a-z])?$/p')
	if [ -z "${_t}" ]; then
		log_debug "verify_dns_name: name starts of ends with hyphen"
		return 1
	fi
	# check IDNA / Punycode
	_t=$(echo "${_dns}" | ${SED} -n -E '/^xn--/p')
	if [ -n "${_t}" -a "${PERMIT_IDNA}" -eq 0 ]; then
		log_debug "verify_dns_name: name contains IDNA characters. disabled by policy"
		return 1
	fi
	# check reserved TLDs
	_t=$(echo "${_dns}" | ${SED} -n -E '/'${RESERVED_TLDS}'$/p')
	if [ -n "${_t}" -a "${PERMIT_RESERVED_TLDS}" -eq 0 ]; then
		log_debug "verify_dns_name: name contains reserved TLD. disabled by policy"
		return 1
	fi
	# check for IP format
	# NOTE: RE is just 'ok' for IP. Plenty of non-IP will get caught, but that's ok
	_t=$(echo "${_dns}" | ${SED} -n -E '/^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/p')
	if [ -n "${_t}" ]; then
		log_debug "verify_dns_name: IP formated SAN"
		return 1
	fi
	#NOTE: if we start accepting IP: based SANS... add the following checks
	#	address is not one of: private, loopback, link_local, unspecified,
	#	  multicast, broadcast
	#	address is actually a valid IP address
	return 0
}

verify_cert_req() {
	local _sans _s _n _typ _dns _reqfile _valid_names
	_reqfile=$1; shift
	_valid_names=$*
	_sans=$(extract_san "${_reqfile}" "req")
	if [ $? -ne 0 ]; then
		log_debug "verify_cert_req: error extracting SAN"
		return 1
	fi
	_valid_names=$(lc "${_valid_names}")
	for _s in $( echo "${_sans}" | ${TR} ',' '\n'); do
		_typ=$(echo "${_s}" | ${CUT} -f1 -d: | uc)
		_dns=$(echo "${_s}" | ${CUT} -f2 -d: | lc)
		# make sure that the SAN is DNS... we do not support other types
		if [ "${_typ}" != "DNS" ]; then
			log_debug "verify_cert_req: unsupported SAN type ${_typ}"
			return 1
		fi
		# check name against list of valid names
		if [ -n "${_valid_names}" ]; then
			local _f=0
			for _n in $(echo -n "${_valid_names}" | ${TR} ', ' '\n\n'); do
log_debug "verify_cert_req: checking name against ${_n}"
				if [ "${_n}" == "${_dns}" ]; then
					_f=1
					break;
				fi
			done
			if [ $_f -eq 0 ]; then
				log_debug "verify_cert_req: name not found in valid list: ${_dns} not in ${_valid_names}" 
				return 1
			fi
		fi
		# verify name is actually valid
		verify_dns_name "${_dns}"
		if [ $? -ne 0 ]; then
			log_debug "verify_cert_req: dns name invalid"
			return 1
		fi
	done
	# no errors
	return 0
}

jwk_to_pem() {
	local _kty _sig _pem _jwk
	_jwk=$1
	if [ -z "${_jwk}" ]; then
		log_debug "jwk_to_pem: no jwk"
		return 1
	fi

	_kty=$(echo "${_jwk}" | ${JQ} -cr '.kty // ""')
	if [ $? -ne 0 -o -z "${_kty}" ]; then
		log_debug "jwk_to_pem: failed get kty"
		return 1
	fi
	case "${_kty}" in
		EC)
			local _x _y _crv
			_crv=$(echo "${_jwk}" | ${JQ} -cr '.crv // ""')
			if [ $? -ne 0 -o -z "${_crv}" ]; then
				log_debug "jwk_to_pem: failed get crv"
				return 1
			fi
			_x=$(echo "${_jwk}" | ${JQ} -cr '.x // ""')
			if [ $? -ne 0 -o -z "${_x}" ]; then
				log_debug "jwk_to_pem: failed get x"
				return 1
			fi
			_y=$(echo "${_jwk}" | ${JQ} -cr '.y // ""')
			if [ $? -ne 0 -o -z "${_y}" ]; then
				log_debug "jwk_to_pem: failed get y"
				return 1
			fi
			_pem=$(_jwk_ec_public_pem "${_crv}" "${_x}" "${_y}")
			if [ $? -ne 0 ]; then
				log_debug "jwk_to_pem: generate EC PEM"
				return 1
			fi
			;;
		RSA)
			local _n _e
			_n=$(echo "${_jwk}" | ${JQ} -cr '.n // ""')
			if [ $? -ne 0 -o -z "${_n}" ]; then
				log_debug "jwk_to_pem: failed get n"
				return 1
			fi
			_e=$(echo "${_jwk}" | ${JQ} -cr '.e // ""')
			if [ $? -ne 0 -o -z "${_e}" ]; then
				log_debug "jwk_to_pem: failed get e"
				return 1
			fi
			_pem=$(_jwk_rsa_public_pem "${_n}" "${_e}")
			if [ $? -ne 0 ]; then
				log_debug "jwk_to_pem: generate RSA PEM"
				return 1
			fi
			;;
		*)	# unsupported type
			log "ERROR" "jwk_to_pem: unsupported signature type: ${_kty}"
			return 1
			;;
	esac
	echo "${_pem}"
	return 0
}

verify_signature() {
	local _sigfile _ret _hash _jwk64 _alg _sig _pemfile
	local _jwk64=$1
	local _alg=$2
	local _sig=$3
	local _pemfile=$4
	if [ -z "${_alg}" -o -z "${_sig}" -o -z "${_pemfile}" ]; then
		log_debug "verify_signature: missing required fields"
		return 1
	fi
	case "${_alg}" in
		*256) _hash="-sha256" ;;
		*384) _hash="-sha384" ;;
		*512) _hash="-sha512" ;;
		*)
			log "ERROR" "verify_signature: hash not supported: ${_alg}"
			return 1
			;;
	esac
	_sigfile=$(${MKTEMP} -t "acme-sig.XXXXXXX" 2>&1)
	if [ $? -ne 0 ]; then
		log_debug "verify_signature: failed to make temp file ${_sigfile}"
		return 1
	fi
	# save sig to file in DER format
	sig_to_der "${_sig}" "${_alg}" > "${_sigfile}"
	if [ $? -ne 0 ]; then
		log_debug "validate_jws: failed to save signature to tmpfile"
		${RM} -f "${_sigfile}"
		return 1
	fi
	# verify the signature
	_ret=$(echo -n "${_jwk64}" | ${OSSL} dgst "${_hash}" -verify "${_pemfile}" -signature "${_sigfile}")
	if [ $? -ne 0 ]; then
		log "ERROR" "verify_signature: failed verify signature"
		log_debug "alg: ${_alg}"
		log_debug "jwk64: ${_jwk64}"
		log_debug "keyfile: $(${CAT} "${_pemfile}")"
		log_debug "signature: $(${CAT} "${_sigfile}" | ${OSSL} enc -a -A)"
		log_debug "validate_jws: signature verify failed: ${_ret}"
		#${CAT} ${_sigfile} | ${OSSL} asn1parse -inform DER -dump >&2
		${RM} -f "${_sigfile}"
		return 1
	fi
	${RM} -f "${_sigfile}"
	return 0
}

# see section 6.2
# validate the JSON Web Signature
validate_jws() {
	local _pem _pemfile _acct _alg _jwk64 _kid
	_jwk64=$(echo -n "${_JWK64}" | ${TR} -d '\n\r\t ')
	_acct=$(jwk_to_acct)
	if [ $? -ne 0 ]; then
		# jwk not in request... look for kid
		_kid=$(query_req_field '.protected | .kid // ""')
		if [ -z "${_kid}" ]; then
			return 1
		fi
		_acct=$(extract_id "${_kid}")
	fi
	if [ -z "${_acct}" ]; then
		# account not found
		return 1
	fi
	log "WARN" "validate_jws: looking up account: ${_acct}"
	_alg=$(query_req_field '.protected | .alg')
	if [ $? -ne 0 ]; then
		log_debug "validate_jws: failed get alg"
		return 1
	fi
	_pemfile="${ACME_DIR}/accts/${_acct}.pem"
	# if PEM file has not been created... create and save it.
	if [ ! -f "${_pemfile}" ]; then
		_jwk=$(query_req_field '.protected | .jwk // ""')
		if [ $? -ne 0 -o -z "${_jwk}" ]; then
			log_debug "validate_jws: failed get jwk"
			return 1
		fi
		_pem=$(jwk_to_pem "${_jwk}")
		if [ $? -ne 0 -o -z "${_pem}" ]; then
			log_debug "validate_jws: failed gen pem"
			return 1
		fi
		# save pem file for future
		echo -n "$_pem" > "${_pemfile}"
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
		n=$(query_req_field '.protected | .jwk // ""')
		if [ -n "$n" ]; then
			o=$(query_account_field "${_acct}" '.jwk')
			if [ "$n" != "$o" ]; then
				echo "n: $n" >&2
				echo "o: $o" >&2
				return_error 500 "serverInternal" "old and new jwk don't match"
			fi
		fi
	fi
	_sig=$(query_req_field '.signature')
	if [ $? -ne 0 ]; then
		log "ERROR" "validate_jws: failed get signature"
		return 1
	fi
	verify_signature "${_jwk64}" "${_alg}" "${_sig}" "${_pemfile}"
	if [ $? -ne 0 ]; then
		log "ERROR" "validate_jws: error verifying signature"
		return 1
	fi
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

process_revoke() {
#	local _o=$1
	local _tmpfile
	local _reason
	local _rc=0
#	if [ -z "${_o}" ]; then
#		echo "process_csr: no order provided"
#		return 1
#	fi
	_reason=$(query_req_field '.payload | .reason // ""')
	if [ $? -ne 0 ]; then
		echo "process_revoke: looking for reason field failed"
		return 3
	fi
	_tmpfile=$(${MKTEMP} -t "acme-revoke.XXXXXXXX") || return 99
	# Must add the ---- to begginging and end, and unprotect the CERT and wrap
	# the lines on 64 character boundary
	echo "-----BEGIN CERTIFICATE-----" > "${_tmpfile}"
	${CAT} ${_REQ_FILE} | ${JQ} -r '.payload | .certificate' | url_unprotect | ${FOLD} -w 64 >> "${_tmpfile}"
	# make sure we are on a new line
	echo >> ${_tmpfile}
	echo "-----END CERTIFICATE-----" >> "${_tmpfile}"
	_ret=$(${CA_HELPER} "revoke" "${_tmpfile}" "${_reason}")
	if [ $? -ne 0 ]; then
		echo "process_revoke: error revoking certificate: ${_ret}"
#		${CAT} "${_tmpfile}" >&2
		${RM} -f "${_tmpfile}"
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
	${RM} -f "${_tmpfile}"
	return ${_rc}	
}

process_csr() {
	local _ret _o
	_o=$1
	if [ -z "${_o}" ]; then
		echo "process_csr: no order provided"
		return 1
	fi
	if [ ! -f "${ACME_DIR}/certs/${_o}.req" ]; then
		echo "process_csr: csr file not found"
		return 1
	fi
	_ret=$(${CA_HELPER} "sign" "${ACME_DIR}/certs/${_o}.req" "${ACME_DIR}/certs/${_o}.pem" "${MAX_CERT_DAYS}")
	if [ $? -ne 0 ]; then
		echo "process_csr: error signing CSR: ${_ret}"
		return 1
	fi
	return 0	
}

jwk_to_key() {
	local _a=$1
	_a=$(echo -n "${_a}" | ${TR} -d " " | ${OSSL} dgst -sha256 | cut -f2 -d' ')
	echo "$_a"
}

jwk_to_acct() {
	local _a
	_a=$(query_req_field '.protected | .jwk // ""')
	if [ -z "${_a}" ]; then
		return 1
	fi
	_a=$(jwk_to_key "${_a}")
	echo "${_a}"
	return 0
}

# output error to STDOUT
gen_thumbprint() {
	local _ret _jwk _acct
	_acct=$1
	if [ -z "${_acct}" ]; then
		echo "account not specified"
		return 1
	fi
	_jwk=$(query_account_field "${_acct}" '.jwk // ""')
	if [ $? -ne 0 ]; then
		echo "error query_account_field"
		return 1
	fi
	if [ -z "${_jwk}" ]; then
		echo "failed to retrieve jwk"
		return 1
	fi
	_ret=$(echo -n "${_jwk}" | ${TR} -d " " | ${OSSL} dgst -sha256 -binary | ${OSSL} base64 -a | url_protect)
	echo "${_ret}"
}

# See section 8.3
compare_http_token() {
	local _tmb _acct _token _cmp
	_acct=$1; shift
	_token=$1; shift
	_cmp=$1; shift
	_tmb=$(gen_thumbprint "${_acct}")
	if [ $? -ne 0 ]; then
		log_debug "compare_http_token: gen_thumbprint failed ${_tmb}"
		return 1
	fi
	if [ "${_token}.${_tmb}" == "${_cmp}" ]; then
		log_debug "compare_http_token: ${_token}.${_tmb} == ${_cmp}"
		return 0
	fi
	log_debug "compare_http_token: ${_token}.${_tmb} != ${_cmp}"
	return 1
}

# See section 8.4
compare_dns_token() {
	local _tmb _cmp _acct _token _cl
	_acct=$1; shift
	_token=$1; shift
	_cl=$1; shift
	_tmb=$(gen_thumbprint "${_acct}")
	if [ $? -ne 0 ]; then
		log_debug "compare_dns_token: gen_thumbprint failed ${_tmb}"
		return 1
	fi
	log_debug "compare_dns_token: thumbprint ${_tmb}"
	_cmp=$(echo -n "${_token}.${_tmb}" | ${OSSL} dgst -sha256 -binary | ${OSSL} enc -a -A | url_protect)
	if [ "${_cl}" == "${_cmp}" ]; then
		log_debug "compare_dns_token: ${_cl} == ${_cmp}"
		return 0
	fi
	log_debug "compare_dns_token: ${_cl} != ${_cmp}"
	return 1
}

process_http01_request() {
	local _resp _tmpfile _host _acct _token _retry _delay _timout _rc x _val
	_host=$1
	_acct=$2
	_token=$3
	_retry=${4:-1}
	_delay=${5:-5}
	_timout=${6:-5}
	_rc=1
	if [ -z "${_host}" -o -z "${_acct}" -o -z "${_token}" ]; then
		log_debug "process_http01_request: host or account or token empty"
		return 1
	fi
	_tmpfile=$(${MKTEMP} -t "acme-challenge-${_host}.XXXXXXXX") || return 99
	while [ "${_retry}" -gt 0 ]; do
#		_resp=$(${HTTPLOOKUP} -w ${_timout} -U "ACME.cgi challenge test" -o ${_tmpfile} "http://${_host}/.well-known/acme-challenge/${_token}" 2>&1)
		_resp=$(${HTTPLOOKUP} --silent --connect-timeout "${_timout}" -A "ACME.cgi challenge test" -o "${_tmpfile}" "http://${_host}/.well-known/acme-challenge/${_token}" 2>&1)
		if [ $? -ne 0 ]; then
			log_debug "process_http01_request: error looking up record. ${_resp}"
			${PRINTF} '{"type": "connection", "desc": "%s" }' "${_resp}"
			# ok to loop
		else
			_val=$(${CAT} "${_tmpfile}")
			log_debug "process_http01_request: retreived value: ${_val}"
			x=$(compare_http_token "${_acct}" "${_token}" "${_val}")
			if [ $? -eq 0 ]; then
				_rc=0
				break;
			fi
			# retreive succeeded... but token match failed
			${PRINTF} '{"type": "connection", "desc": "tokens do not match" }'
			break;
		fi
		log_debug "process_http01_request: sleeping for ${_delay} retry ${_retry}"
		${SLEEP} "${_delay}"
		_retry=$((_retry-1))
	done
	${RM} -f "${_tmpfile}"
	log_debug "process_http01_request: return ${_rc}"
	return ${_rc}
}

process_dns01_request() {
	local _resp _host _acct _token _retry _delay _timout _rc
	_host=$1
	_acct=$2
	_token=$3
	_retry=${4:-1}
	_delay=${5:-5}
	_timout=${6:-5}
	_rc=1
	if [ -z "${_host}" -o -z "${_token}" ]; then
		log_debug "process_dns01_request: host or token empty"
		${PRINTF} '{"type": "incorrectResponse, "desc": "tokens" }'
		return 1
	fi
	while [ "${_retry}" -gt 0 ]; do
		_resp=$(${DNSLOOKUP} -t TXT -W "${_timout}" "_acme-challenge.${_host}")
		case "${_resp}" in
			*"not found"*)
				;;
			*"no TXT"*)
				;;
			*"descriptive text"*)
				_resp=$(echo -n "${_resp}" | cut -f4 -d' ' | tr -d '"')
				x=$(compare_dns_token "${_acct}" "${_token}" "${_resp}")
				if [ $? -eq 0 ]; then
					_rc=0
					break;
				fi
				# retreive succeeded... but token match failed
				${PRINTF} '{"type": "incorrectResponse, "desc": "tokens do not match" }'
				break;
				;;
		esac
		log_debug "process_dns01_request: sleeping for ${_delay} retry ${_retry}"
		${SLEEP} "${_delay}"
		_retry=$((_retry-1))
	done
	log_debug "process_dns01_request: return ${_rc}"
	return ${_rc}
}

process_challenge() {
	local _status _acct _i _ret _rc challenges target _chal _rc
	_chal=$1
	_rc=0
	log "INFO" "process_challenge: ${_chal}"
	if [ ! -f "${ACME_DIR}/challenges/${_chal}" ]; then
		log "ERROR" "process_challenge: cannot find challenge ${_chal}"
		exit 1
	fi
	_status=$(query_challenge_field "${_chal}" '.status // ""')
	if [ "${_status}" != "pending" ]; then
		log_debug "process_challenge: status ${_status}"
		log "INFO" "process_challenge: order ${_chal} status ${_status}"
		exit 1
	fi
	set_challenge_field "${_chal}" '.status = "processing"'
	if [ $? -ne 0 ]; then
		log_debug "failed to set status to processing"
		log "ERROR" "process_challenge: failed to set state of order ${_chal} to processing"
		exit 1
	fi
	_acct=$(echo "${_chal}" | cut -f1 -d"_")
	challenges=$(query_challenge_field "${_chal}" '.challenges[] | "\(.type):\(.status):\(.token)" // "" ')
	if [ -z "${challenges}" ]; then
		log "ERROR" "process_challenge: no challenges found for order ${_chal}"
		exit 1
	fi
	_order=$(echo -n "${_chal}" | ${CUT} -f1-2 -d_)
	_i=$(echo -n "${_chal}" | ${CUT} -f4 -d_)
	target=$(query_order_field "${_order}" '.identifiers['${_i}'] | .value // ""')
	if [ -z "${target}" ]; then
		log "ERROR" "process_challenge: no target found in indentifer for order ${_order}"
		exit 1
	fi
	# sanitize target
	verify_dns_name "${target}"
	if [ $? -ne 0 ]; then
		log "ERROR" "process_challenge: target ${target} on invalid list for order ${_order}"
		exit 1
	fi
	log_debug "process_challenge: challenges: ${challenges} for target ${target}"
	# loop thru all challenges and try them
	_i=0
	for _x in ${challenges}; do
		local typ chal_status token
		typ=$(echo "$_x" |cut -f1 -d:)
		chal_status=$(echo "$_x" |cut -f2 -d:)
		token=$(echo "$_x" |cut -f3 -d:)
		if [ "${chal_status}" == "valid" ]; then
			# already validated the challenge...
			log_debug "process_challenge: challenge already validated. skipping"
			continue;
		fi
		case "$typ" in
			"dns-01")
				_ret=$(process_dns01_request "${target}" "${_acct}" "${token}" "${VERIFY_RETRIES}" "${VERIFY_DELAY}" "${VERIFY_TIMEOUT}")
				_rc=$?
				if [ ${_rc} -eq 0 ]; then
					log "INFO" "process_challenge: ${_chal} success"
					break;
				fi
				;;
			"http-01")
				_ret=$(process_http01_request "${target}" "${_acct}" "${token}" "${VERIFY_RETRIES}" "${VERIFY_DELAY}" "${VERIFY_TIMEOUT}")
				_rc=$?
				if [ ${_rc} -eq 0 ]; then
					# success... so break loop
					log "INFO" "process_challenge: ${_chal} success"
					break
				fi
				;;
			*)
				log "ERROR" "process_challenge error: unknown type ${typ}"
				_rc=1
				;;
		esac
		# record the status... should only be failed challenges
		if [ "${_rc}" -ne 0 ]; then
			set_challenge_field "${_chal}" '.challenges['${_i}'].status = "invalid"'
			if [ $? -ne 0 ]; then
				log "ERROR" "process_challenge: failed to set challenge status to invalid after unsuccessful test"
				log_debug "process error: ${_ret}"
				_rc=1
				break;
			fi
			set_challenge_field "${_chal}" '.status = "invalid"'
			if [ $? -ne 0 ]; then
				log "ERROR" "process_challenge: failed to set challenge status to invalid after unsuccessful test"
				log_debug "process error: ${_ret}"
				_rc=1
				break;
			fi
#			set_challenge_field "${_chal}" '.error = ("'${_ret}'" | fromjson)'
			set_challenge_field "${_chal}" '.error = {"type":"connnect","desc":"error"}'
			if [ $? -ne 0 ]; then
				log "ERROR" "process_challenge: failed to set challenge error after unsuccessful test"
				log_debug "process error: ${_ret}"
				_rc=1
				break;
			fi
			log "WARN" "process_challenge: ${_chal} failed"
			_rc=1
			break;
		fi
		# inc to move onto next challenge
		_i=$((_i+1))
	done
	# process successful the response
	if [ "${_rc}" -eq 0 ]; then
		# $i should have the value from the last successful test.
		set_challenge_field "${_chal}" '.challenges['${_i}'].status = "valid"'
		if [ $? -ne 0 ]; then
			log "ERROR" "process_challenge: failed to set challenge status to valid after successful test"
			exit 1
		fi
		set_challenge_field "${_chal}" '.status = "valid"'
		if [ $? -ne 0 ]; then
			log "ERROR" "process_challenge: failed to set challenge status to valid after successful test"
			exit 1
		fi
		set_challenge_field "${_chal}" '.validated = "'$(epoch_to_rfc3339 "$(now_epoch)")'"'
		if [ $? -ne 0 ]; then
			log "ERROR" "process_challenge: failed to set challenge valiadted to time after successful test"
			exit 1
		fi
		log "INFO" "process_challenge end: ${_chal}"
		exit 0
	fi
	# we had all failures
	log "ERROR" "process_challenge: error processing order"
	exit 1
}

return_error() {
	local _hc _ec _msg
	_hc=$1; shift
	_ec=$1; shift
	_msg=$*
#	local _t=$(err_to_hc $_ec)
#	_hc=${_t:-$_hc}
	log "ERROR" "${_ec}: ${_msg}"
	set_header 'Content-Type: application/problem+json'
	_BODY='{"type":"urn:ietf:params:acme:error:'${_ec}'","detail":"'${_msg}'"}'
	log_debug "return_error: req: $(${CAT} "${_REQ_FILE}")"
	return_result "${_hc}" ""
	# no return
}

#DESC: output the return state, header and body(if any)
#NOTE: no return
return_result() {
	local _h _hc _msg _len
	_hc=$1; shift
	_msg=$*
	_len=0
	# set the Link header
	set_header "Link: <${ISSUER_URL}/directory>;rel=\"index\""
	# return the HTTP status back to CGI interperter
	echo "Status: ${_hc} $(hc_string "${_hc}")"
	# output the headers
	for _h in "${_HEADERS[@]}"; do
		echo "${_h}"
	done
#XXX this breaks things
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
	local _d _dir DIRS
	_dir=$1
	DIRS="$_dir $_dir/nonce $_dir/orders $_dir/certs $_dir/accts"
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
	local _fun _rcvd_url _exp_url _cmp
	_fun=$1
	_rcvd_url=$(query_req_field '.protected | .url')
	_exp_url="${ISSUER_URL}/${_fun}"
	# compare the expected url with the received url.  if they match
	# the compare string will be empty or contain just the trailing
	# part of the url
	_cmp=${_rcvd_url##"$_exp_url"}
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
	local _nt _ct _rc nonce
	_nt=0
	_ct=$(now_epoch)
	_rc=1
	nonce=$(query_req_field '.protected | .nonce')
	if [ -z "${nonce}" ]; then
		return $_rc
	fi
	if [ -f "${ACME_DIR}/nonce/${nonce}" ]; then
		_nt=$(${CAT} "${ACME_DIR}/nonce/${nonce}")
		if [ -n "${_nt}" ]; then
			if [ "$((_nt + NONCE_EXPIRE))" -gt "${_ct}" ]; then
				_rc=0
			fi
		fi
		# remove old nonce
		${RM} -f "${ACME_DIR}/nonce/${nonce}"
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
		if [ ! -f "${ACME_DIR}/nonce/${_n}" ]; then
			now_epoch > "${ACME_DIR}/nonce/${_n}"
#			${DATE} +"%s" >${ACME_DIR}/nonce/${_n}
			set_header "Replay-Nonce: ${_n}"
			return 0
		fi
		_f=$((_f-1))
	done
	log "ERROR" "make_nonce: failed to create nonce"
	return 1
}

# RETURN: 0 on success 1 on error
# ECHO: error_class message
verify_acct() {
	local acct
	local status
	acct=$(query_req_field '.protected | .kid // ""')
	if [ -z "${acct}" ]; then
		acct=$(jwk_to_acct)
		if [ -z "${acct}" ]; then
			log "ERROR" "verify_acct: no kid or jwk found in request"
			echo "malformed" "no kid or jwk found in request"
			return 1
		fi
	else
		acct=$(extract_id "${acct}")
#		acct=${acct##*/acct/}
#		echo "${acct}" | grep -qE '^[a-zA-Z0-9_-]+$'
#		if [ $? -ne 0 ]; then
#			log_debug "verify_acct: error id: '$_r'"
#			echo "malformed" "invalid id"
#			return 1
#		fi
	fi
	log_debug "verify_acct: found account ${acct}"
	if [ ! -f "${ACME_DIR}/accts/${acct}" ]; then
		log "ERROR" "verify_acct: Account ${acct} does not exist."
		echo "accountDoesNotExist" "cannot find existing account"
		return 1
	else
		# check the account status
		status=$(query_account_field ${acct} '.status // ""')
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
	local acct ore contacts new_contact status
	make_nonce || return_error 500 "badNonce" "failed to create new nonce"
	# check for account without a trailing slash "/".  if true, this is a new request
	acct=${REQUEST_URI##*/acct}	
	if [ -z "${acct}" ]; then
		# no account info sent
		log "INFO" "account: new request"
		# new account request
		acct=$(jwk_to_acct)
		if [ ! -f ${ACME_DIR}/accts/${acct} ]; then
			ore=$(query_req_field '.payload | .onlyReturnExisting // ""')
			if [ -n "${ore}" -a "${ore}" == "true" ]; then
				#NOTE: if this is the firest time the client is making the request, the account object
				#      will not be created... but the PEM file has already been by validat_jws().  So
				# 	   check and delete it if it's alone.
				if [ -f "${ACME_DIR}/accts/${acct}.pem" -a ! -f "${ACME_DIR}/accts/${acct}" ]; then
					${RM} -f "${ACME_DIR}/accts/${acct}.pem"
				fi
				log_debug "handle_account: ignore new account creation per client request"
				log "INFO" "Account lookup for ${acct} requested.  Does not exist."
				return_error 400 "accountDoesNotExist" "account creation ignored at client request"
			fi
			# check contacts
			contacts=$(query_req_field '.payload | .contact[] // ""')
			if [ -z "${contacts}" ]; then
				log_debug "handle_account: no contacts specified"
				log "ERROR" "No contacts specified for new account ${acct}"
				return_error 424 "invalidContact" "no contact informaton supplied"
				# no return
			fi
			log_debug "handle_account: creating new account"
			_BODY='{
"status": "valid", 
"orders": "'${ISSUER_URL}'/orders/'${acct}'", 
"termsOfServiceAgreed": "'$(query_req_field '.payload | .termsOfServiceAgreed')'", 
"contact": '$(query_req_field '.payload | .contact')', 
"jwk": '$(query_req_field '.protected | .jwk')'
}'
			echo "$_BODY" > "${ACME_DIR}/accts/${acct}"
			if [ $? -ne 0 ]; then
				log_debug "handle_account: failed to save account"
				log "ERROR" "failed to save account ${acct}"
				return_error 500 "serverInternal" "failed to save account"
				# return
			fi
			_BODY=$(${CAT} "${ACME_DIR}/accts/${acct}")
			set_header "Location: ${ISSUER_URL}/acct/${acct}"
			log "INFO" "Account ${acct} created"
			return_result 201 "Created"
			# no return
		else
			# account already exists
			log_debug "handle_account: account already exists"
			log "INFO" "Account ${acct} already exists."
			set_header "Location: ${ISSUER_URL}/acct/${acct}"
			_BODY=$(${CAT} "${ACME_DIR}/accts/${acct}")
			return_result 200 "Ok"
			# no return
		fi
	else
		# existing account request
		acct=$(verify_acct) || return_error 400 "${acct}"
		log "INFO" "account: update request ${acct}"
		# check the account status
		status=$(query_account_field "${acct}" '.status') || return_error 404 "serverInternal" "missing account info"
		log_debug "handle_account: account status ${status}"
		case "${status}" in
			deactivated)
				log "ERROR" "account state deactivated"
				return_error 400 "unauthorized" "account ${acct} is ${status}"
				# no return
				;;
			valid)
				log "INFO" "account state valid"
				# just fall thru
				;;
			*)
				log "ERROR" "account state unknown: ${status}"
				return_error 404 "accountNotValid" "account ${acct} is ${status}"
				# no return
				;;
		esac
		# update account info...
		status=$(query_req_field '.payload | .status //""')
		if [ -n "${status}" ]; then
			if [ "${status}" != "deactivated" ]; then
				# only permit client to deactivate account
				log "ERROR" "account deactivated: update denied"
				return_error 400 "unauthorized" "invalid request to set status to ${status}"
				# no return
			fi
			log_debug "handle_account: set account status to ${status}"
			set_account_field "${acct}" '.status = "'${status}'"' || return_error 404 "serverInternal" "error updating account status"
			log "INFO" "account status updated to ${status}"
		else
			new_contact=$(query_req_field '.payload | .contact // ""')
			log_debug "handle_account: set account contact to ${new_contact}"
			if [ -n "${new_contact}" ]; then
				set_account_field "${acct}" '.contact = "'${new_contact}'"' || return_error 404 "serverInternal" "error updating account contact"
				log "INFO" "account contacts updated"
			fi
		fi
		_BODY=$(${CAT} "${ACME_DIR}/accts/${acct}")
		set_header "Location: ${ISSUER_URL}/acct/${acct}"
		log "INFO" "account ${acct} updated."
		return_result 200 "OK"
		# no return
	fi
	log "ERROR" "account ${acct} process error."
	return_error 400 "serverInternal" "internal error when processing account"
	# no return
}

# DESC: return a list of orders for a specified account
handle_orders() {
	local acct status olist
	make_nonce || return_error 400 "badNonce" "failed to create new nonce"
	# abusing the acct response
	acct=$(verify_acct) || return_error 400 "${acct}"
	olist=$(${LS} -1r "${ACME_DIR}/orders/${acct}_*" | ${JQ} -Rs '. | split("\n") | map(select (. != "")) | map("'${ISSUER_URL}'/order" + .) | { orders: .}')
	log_debug "handle_orders: orders ${olist}"
	_BODY="${olist}"
	log "INFO" "orders list returned"
	return_result 200 "OK"
	# no return
}

handle_key_change() {
	local acct oacct _jwk nacct na_pro na_pay na_sig jwk64 _alg okey url nurl _pem _pemfile
#### NOT TESTED
	log "INFO" "keychange: request"
	make_nonce || return_error 400 "badNonce" "failed to create new nonce"
	# abusing the acct response
	acct=$(verify_acct) || return_error 400 "${acct}"
	# The request has now been validated from the old key and the account is good.
	# on all errors abort
	# Verify that payload.signature has signed payload.protected & payload.payload
	na_pro=$(query_req_field '.payload | .protected // ""')
	na_pay=$(query_req_field '.payload | .payload // ""')
	na_sig=$(query_req_field '.payload | .signature // ""')
	jwk64="${na_pro}.${na_pay}"
	na_pro=$(url_unprotect "${na_pro}" | ${OSSL} -a -A -d)
	na_pay=$(url_unprotect "${na_pay}" | ${OSSL} -a -A -d)
	if [ -z "${na_pro}" -o -z "${na_pay}" -o -z "${na_sig}" ]; then
		log "ERROR" "keychange: cannot extract new account information"
		return_error 400 "malformed" "cannot extract new account information"
		# no return
	fi
	#	check the signature
	_alg=$(echo "${na_pro}" | ${JQ} -cr '.alg //')
	if [ -z "${_alg}" ]; then
		log "ERROR" "keychange: cannot find alg"
		return_error 400 "malformed" "cannot extract alg"
		# no return
	fi
	verify_signature "${jwk64}" "${_alg}" "${_sig}" "${_pemfile}"
	if [ $? -ne 0 ]; then
		log "ERROR" "keychange: error verifying signature"
		return 1
	fi
	# 	Extract payload.payload.account and make sure it matches the current account
	oacct=$(echo "${na_pay}" | ${JQ} -cr '.account // ""')
	if [ -z "${oacct}" ]; then
		log "ERROR" "keychange: old account missing"
		return_error 400 "malformed" "missing old account"
	fi
	oacct=$(extract_id "${oacct}")
	if [ "${acct}" != "${oacct}" ]; then
		log_debug "handle_key_change: old account mismatch: ${acct} != ${oacct}"
		log "ERROR" "keychange: old account does not match"
		return_error 400 "malfomed" "old account does not match"
		# no return
	fi
	# 	Extract the old key from the payload.protected.payload.oldkey and confirm it
	# 		matches the old key 
	okey=$(echo "${na_pay}" | ${JQ} -cr '.oldKey // ""')
	if [ -z "${okey}" ]; then
		log "ERROR" "keychange: old key missing"
		return_error 400 "malformed" "missing old key"
	fi
	oacct=$(jwk_to_key "${okey}")
	if [ "${acct}" != "${oacct}" ]; then
		log_debug "handle_key_change:  key mismatch: ${acct} != ${oacct}"
		log "ERROR" "keychange: old key does not match account"
		return_error 400 "malfomed" "old key does not match account"
		# no return
	fi
	#	Verify that play.protected.url == the protected.url
	url=$(query_req_field '.protected | .url // ""')
	if [ -z "${url}" ]; then
		log "ERROR" "keychange: request url missing"
		return_error 400 "malformed" "request url missing"
		# no return
	fi
	nurl=$(echo "${na_pro}" | ${JQ} -cr '.url // ""')
	if [ -z "${nurl}" ]; then
		log "ERROR" "keychange: request url missing"
		return_error 400 "malformed" "request url missing"
		# no return
	fi
	if [ "${url}" != "${nurl}" ]; then
		log_debug "handle_key_change: old url mismatch: ${url} != ${nurl}"
		log "ERROR" "keychange: old url does not match request"
		return_error 400 "malfomed" "old url does not match request"
		# no return
	fi
#HERE where is nacct set?
	#	check to see if an account exists with the new key. if so error with 409 (conflict)
	if [ -f "${ACME_DIR}/accts/${nacct}" ]; then
		log_debug "handle_key_change: new account already exists: ${nacct}"
		log "ERROR" "keychange: new account already exists"
		return_error 409 "conflict" "new account already exists"
		# no return
	fi
	_jwk=$(echo "${na_pro}" | ${JQ} -cr '.jwk // ""')
	if [ -z "${_jwk}" ]; then
		log "ERROR" "keychange: new key not found"
		return_error 400 "malfomed" "new key not found"
		# no return
	fi
	#	read account old in... update jwk in account.
	_BODY=$(${CAT} "${ACME_DIR}/accts/${acct}")
	_BODY=$(echo "${_BODY}" | ${JQ} -cr '.jwk = ('${_jwk}' | fromjson )')
	#	write out to new account.
	echo "${_BODY}" > "${ACME_DIR}/accts/${nacct}"
	if [ $? -ne 0 ]; then
		log "ERROR" "keychange: error writing new account: ${nacct}"
		return_error 400 "serverInternal" "error writing new account"
		# no return
	fi
	#	write out PEM for new account.
	_pemfile="${ACME_DIR}/accts/${nacct}.pem"
	_pem=$(jwk_to_pem "${_jwk}")
	if [ $? -ne 0 -o -z "${_pem}" ]; then
		log "ERROR" "keychange: error generating pem from jwk"
		return_error 400 "serverInternal" "error writing new account"
		# not reached
	fi
	# save pem file for future
	echo -n "$_pem" > "${_pemfile}"
	if [ $? -ne 0 ]; then
		log "ERROR" "keychange: error saving pem"
		return_error 400 "serverInternal" "error writing new account"
		# not reached
	fi
	#	mark old account as "deactivated". cleanup script will take care of it
	set_account_field "${acct}" '.status = "deactivated"'
	if [ $? -ne 0 ]; then
		log "ERROR" "keychange: error deactivating old account ${acct}"
		return_error 400 "serverInternal" "error deactivating old account"
		# no return
	fi
	log "INFO" "keychange: account assigned new key"
	return_result 200 "OK"
	# no return
}

handle_order() {
	local acct status order expire authz now nb max na
	local notBefore notAfter
	local raw_identifiers identifiers _pl wildcard _i t
	local auth_urls=""
	make_nonce || return_error 400 "badNonce" "failed to create new nonce"
	# abusing the acct response
	log "INFO" "order request"
	acct=$(verify_acct) || return_error 400 "${acct}"
	order=$(extract_id)
	_pl=$(query_req_field '.payload // ""')
	# if payload is empty, then client is just looking for current status
	if [ -z "${_pl}" ]; then
		if [ ! -f ${ACME_DIR}/orders/${order} ]; then
			log "ERROR" "order: unknown order ${order}"
			return_error 400 "malformed" "Bad Request"
			# no return
		fi
		_BODY=$(${CAT} ${ACME_DIR}/orders/${order})
		return_result 200 "OK"
		# no return
	fi
	# assume new order
	wildcard=$(query_req_field '.payload | .wildcard // ""')
	# check for wildcard request
	if [ -n "${wildcard}" -a "$(lc "${wildcard}")" == "true" ]; then
		log "ERROR" "order: wildcard requested, not supported"
		return_error 400 "rejectedIdentifier" "wildcards not supported"
	fi
	now=$(now_epoch)
	notBefore=$(query_req_field '.payload | .noBefore // ""')
	if [ -n "${notBefore}" ]; then
		nb=$(rfc3339_to_epoch "${notBefore}")
		if [ "${nb}" -gt "${now}" ]; then
			log "ERROR" "order: notBefore invalid"
			# notBefore is in the future
			return_error 400 "malformed" "Bad Request"
		fi
	fi
	max=$((now + MAX_CERT_TIME))
	notAfter=$(query_req_field '.payload | .noBefore // ""')
	if [ -n "${notAfter}" ]; then
		na=$(rfc3339_to_epoch "${notAfter}")
		if [ "${na}" -gt "${max}" ]; then
			log "ERROR" "order: notAfter invalid"
			# notAfter is longer than MAX_CERT_TIME
			return_error 400 "malformed" "Bad Request"
		fi
	fi
	# verify we can handle the authz
	raw_identifiers=$(query_req_field '.payload | .identifiers')
	identifiers=$(query_req_field '.payload | .identifiers[] | "\(.type):\(.value)"')
	order=$(${OSSL} rand -hex 8)
	_i=0
	for _id in ${identifiers}; do
		t=$(echo "${_id}" | ${CUT} -f1 -d: | lc)
		authz=$(${OSSL} rand -hex 8)
		case "$t" in
			dns)
				auth_urls="${auth_urls}\"${ISSUER_URL}/authz/${acct}_${order}_${authz}_${_i}\" "
				;;
			*)
				log "ERROR" "order: unhandled idnetifier ${t}"
				return_error 404 "unsupportedIdentifier" "do not support ${t} identifiers"
				# no return
				;;
		esac
		_i=$((_i+1))
	done
	auth_urls="[ $(echo "${auth_urls}" | ${SED} -r -e 's/(.*) ?$/\1/' -e 's/ /,/' ) ]"
	expire=$(epoch_to_rfc3339 "$((now + ORDER_EXPIRE))")
	notBefore=$(epoch_to_rfc3339 "${now}")
	notAfter=$(epoch_to_rfc3339 "${max}")
	set_header "Location: ${ISSUER_URL}/order/${acct}_${order}"
	_BODY='{
  "status": "pending",
  "expires": "'${expire}'",
  "notBefore": "'${notBefore}'",
  "notAfter": "'${notAfter}'",
  "identifiers": '${raw_identifiers}',
  "authorizations" : '${auth_urls}',
  "finalize": "'${ISSUER_URL}'/finalize/'${acct}'_'${order}'"
}'
	echo "${_BODY}" > "${ACME_DIR}/orders/${acct}_${order}"
	if [ $? -ne 0 ]; then
		_BODY=""
		log "ERROR" "order: error saving"
		return_result 500 "error saving order"
		#no return
	fi
	# return success to requestor
	log "INFO" "order: new order created ${acct}_${order}"
	return_result 201 "Created"
	# no return
}

handle_authz() {
	local acct status order authz identifier expires token _i challenges
	make_nonce || return_error 400 "badNonce" "failed to create new nonce"
	log "INFO" "authz: request"
	# abusing the acct response
	acct=$(verify_acct) || return_error 400 "${acct}"
	authz=$(extract_id)
	if [ -z "$authz" ]; then
		log "ERROR" "authz: no authz specified"
		return_error 400 "malformed" "no authz in url"
		# no return
	fi
	order=$(echo -n "${authz}" | ${CUT} -f1-2 -d"_")
	log "INFO" "authz: authz ${authz}"
	if [ -f "${ACME_DIR}/challenges/${authz}" ]; then
		log_debug "handle_authz: processing chanllenge ${authz}"
		# just load the file for return.  The status will be updated by the testing functions
		_BODY=$(${CAT} "${ACME_DIR}/challenges/${authz}")
		status=$(query_challenge_field "$authz" '.status // ""')
		case "${status}" in
#			"deactivated")
#				set_order_field "${order}" '.status = "deactivated"'
#				if [ $? -ne 0 ]; then
#					log "ERROR" "authz: could not set order state to deactivated for order ${order}"
#					return_error 501 "serverInternal" "error seting order state to deactivated"
#					# no return
#				fi
#				;;
			"valid")
				# challenge is valid... or set order so to ready so cert can be generated
				set_order_field "${order}" '.status = "ready"'
				if [ $? -ne 0 ]; then
					log "ERROR" "authz: could not set order state to valid for order ${order}"
					return_error 501 "serverInternal" "error seting order state to valid"
					# no return
				fi
				;;
			"invalid")
				set_order_field "${order}" '.status = "invalid"'
				if [ $? -ne 0 ]; then
					log "ERROR" "authz: could not set order state to invalid for order ${order}"
					return_error 501 "serverInternal" "error seting order state to invalid"
					# no return
				fi
				;;
			*)
				log "ERROR" "authz: unknow challenge state ${status} for order${order}"
				return_error 501 "serverInternal" "error seting order state to invalid"
				# no return
				;;
		esac
	else
		log "INFO" "authz: create new challenge"
		token=$(${OSSL} rand -hex 16)
		_i=$(echo -n "${authz}" | ${CUT} -f4 -d_)
		if [ -z "${_i}" ]; then
			return_error 501 "serverInternal" "error cannot find index"
			# no return
		fi
		identifier=$(query_order_field "${order}" ".identifiers[${_i}]") || return_error 500 "serverInternal" "cannt retrieve identifires from order"
		expires=$(query_order_field "${order}" ".expires") || return_error 500 "serverInternal" "cannot retrieve expire from order"
		challenges='[
{ "type": "http-01", "url": "'${ISSUER_URL}'/challenge/'${authz}'", "status": "pending", "token": "'${token}'" },
{ "type": "dns-01", "url": "'${ISSUER_URL}'/challenge/'${authz}'", "status": "pending", "token": "'${token}'" }
]'
		_BODY='{ "status": "pending", "expires": "'${expires}'", "identifier": '${identifier}', "challenges": '${challenges}' }'
		# save challenge document
		echo "$_BODY" > "${ACME_DIR}/challenges/${authz}"
		if [ $? -ne 0 ]; then
			log "ERROR" "authz: failed to save challenge"
			return_error 500 "serverInternal" "error saving challenge object"
			# no return
		fi
	fi
	log "INFO" "authz: success"
	return_result 200 "OK"
	# no return
}

handle_challenge() {
	local acct status authz
	make_nonce || return_error 400 "badNonce" "failed to create new nonce"
	log "INFO" "challenge: request"
	# abusing the acct response
	acct=$(verify_acct) || return_error 400 "${acct}"
	authz=$(extract_id)
	if [ -z "$authz" ]; then
		log "ERROR" "challenge: no authz specified"
		return_error 400 "malformed" "no order in url"
		# no return
	fi
	log "INFO" "challenge: authz ${authz}"
	if [ -f "${ACME_DIR}/challenges/${authz}" ]; then
		status=$(query_challenge_field "${authz}" '.status // ""') return_error 500 "serverInternal" "cannot find status"
		log "INFO" "challenge: status ${status}"
		# Check challenge status...
		case "${status}" in
			"pending")
				set_header "Retry-After: ${CLIENT_RETRY}"
				_BODY=$(query_challenge_field "${authz}" '.challenges // ""') || return_error 500 "serverInternal" "error parsing challenges"
				if [ -z "${_BODY}" ]; then
					# no challenges found...
					log "ERROR" "challenge: no valid challenges found"
					return_error 400 "malformed" "no valid challenges found"
					# no return
				fi
				log "INFO" "challenge: calling process"
				# call ourselves to process the order
				$0 -x "${authz}"
				# actaully return!
				;;
			"processing")
				# still trying
				set_header "Retry-After: ${CLIENT_RETRY}"
				log "WARN" "challenge: alredy processing"
				return_result "204" "No Content"
				# no return
				;;
			"valid")
				# done... return first challenge object that has status of 'valid'
				_BODY=$(query_challenge_field "${authz}" '.challenges | map(select(.status == "valid")) | .[0] // ""') || return_error 500 "serverInternal" "error parsing challenges"
				if [ -z "${_BODY}" ]; then
					log "ERROR" "challenge: no valid challenges found"
					# no challenges found...
					return_error 400 "malformed" "no valid challenges found"
					# no return
				fi
				log "INFO" "challenge: valid"
				return_result 200 "OK"
				# no return
				;;
			"invalid")
				_BODY=$(query_challenge_field "${authz}" '.challenges | map(select(.status == "invalid")) | .[0] // ""') || return_error 500 "serverInternal" "error parsing challenges"
				if [ -z "${_BODY}" ]; then
					log "ERROR" "challenge: no valid challenges found"
					# no challenges found...
					return_error 400 "malformed" "no valid challenges found"
					# no return
				fi
				log "INFO" "challenge: invalid"
				return_result 200 "OK"
				# no return
				;;
			*)
				log "ERROR" "challenge: unhandled status: ${status}"
				return_error 500 "serverInternal" "invalid challenge state: ${status}"
				# no return
				;;
		esac
	else
		log "ERROR" "challenge: invalid challenge ${authz}"
		return_error 401 "invalidChallenge" "cannot find requested challenge"
		# no return
	fi
	log "INFO" "challenge: success"
	return_result 200 "OK"
	# no return
}

handle_finalize() {
	local acct status _csr _ret order _identifiers
	make_nonce || return_error 400 "badNonce" "failed to create new nonce"
	log "INFO" "finalize: process"
	# abusing the acct response
	acct=$(verify_acct) || return_error 400 "${acct}"
	order=$(extract_id)
	if [ -z "$order" ]; then
		log "ERROR" "finalize: no order specified"
		return_error 400 "malformed" "no order in url"
		# no return
	fi
	log "INFO" "finalize: order ${order}"
	if [ -f "${ACME_DIR}/orders/${order}" ]; then
		status=$(query_order_field "${order}" '.status // ""') || return_error 500 "serverInternal" "cannot find order status"
		log_debug "handle_finalize: order status ${status}"
		case "${status}" in
			"ready")
				log "INFO" "finalize: ready"
				set_order_field "${order}" '.status = "processing"'
				if [ $? -ne 0 ]; then
					log "ERROR" "could not set certificate statue to processing on order ${order}"
					return_error 501 "serverInternal" "error setting certificate status to processing"
					# no return
				fi
				_csr=$(query_req_field '.payload | .csr // ""') || return_error 500 "serverInternal" "error extracting the CSR"
				if [ -z "${_csr}" ]; then
					log "ERROR" "finalize: request not found"
					return_error 499 "malformed" "CSR not found in request"
					# no return
				fi
				${PRINTF} "-----BEGIN CERTIFICATE REQUEST-----\n%s\n-----END CERTIFICATE REQUEST-----" \
					"$(url_unprotect "${_csr}" )" > "${ACME_DIR}/certs/${order}.req"
				if [ $? -ne 0 ]; then
					log "ERROR" "finalize: error saving rquest"
					return_error 500 "serverInternal" "error saving csr"
					# no return
				fi
				#NOTE: since the status of the order is valid, we assume all challenges were validated succesfully
				_identifiers=$(query_order_field "${order}" '.identifiers | map (.value) | @sh // ""' | ${TR} -d "'")
				if [ -z "${_identifiers}" ]; then
					log "ERROR" "finalize: cannot retreive identifiers from order"
					return_error 500 "serverInternal" "error retreiving identifiers"
				fi
				# verify that the requested identifiers are in the cert... no more / no less
				verify_cert_req "${ACME_DIR}/certs/${order}.req" "${_identifiers}"
				if [ $? -ne 0 ]; then
					log "ERROR" "finalize: bad request"
					set_order_field "${order}" '.status = "invalid"'
					if [ $? -ne 0 ]; then
						log "ERROR" "could not set certificate statue to ready on order ${order}"
						return_error 501 "serverInternal" "error setting certificate status to ready"
						# no return
					fi
					return_error 400 "badCSR" "${_ret}"
				fi
				_ret=$(process_csr "${order}")
				if [ $? -ne 0 ]; then
					log "ERROR" "finalize: bad request"
					set_order_field "${order}" '.status = "invalid"'
					if [ $? -ne 0 ]; then
						log "ERROR" "could not set certificate statue to ready on order ${order}"
						return_error 501 "serverInternal" "error setting certificate status to ready"
						# no return
					fi
					return_error 400 "badCSR" "${_ret}"
					# no return
				fi
				# set the path to query the certificate
				set_order_field "${order}" '.certificate = "'${ISSUER_URL}'/certificate/'${order}'"'
				if [ $? -ne 0 ]; then
					log "ERROR" "could not set certificate link on order ${order}"
					return_error 501 "serverInternal" "error seting certificate for order"
					# no return
				fi
				# set the order to valid
				set_order_field "${order}" '.status = "valid"'
				if [ $? -ne 0 ]; then
					log "ERROR" "could not set certificate statue to ready on order ${order}"
					return_error 501 "serverInternal" "error setting certificate status to ready"
					# no return
				fi
				_BODY=$(${CAT} "${ACME_DIR}/orders/${order}")
				# drop thru and return OK
				;;
			"valid")
				# order is valid... just return order
				log "INFO" "finalize: valid"
				_BODY=$(${CAT} "${ACME_DIR}/orders/${order}")
				# drop thru and return OK
				;;
			"pending")
				log "ERROR" "finalize: pending"
				return_error 499 "orderNotReady" "order not ready to be finalized"
				# no return
				;;
			"processing")
				# order is processing... just return order
				log "INFO" "finalize: processing"
				_BODY=$(${CAT} "${ACME_DIR}/orders/${order}")
				# drop thru and return OK
				;;
			"invalid")
				log "ERROR" "finalize: invalid"
				return_error 499 "orderNotReady" "order error processing"
				# no return
				;;
			*)
				log "ERROR" "finalize: unhandled status: ${status}"
				return_error 500 "serverInternal" "invalid order state: ${status}"
				# no return
				;;
		esac
	else
		log "ERROR" "finalize: invalid request"
		return_error 401 "invalidChallenge" "cannot find requested order"
		# no return
	fi
	log "INFO" "finalize: success"
	return_result 200 "OK"
	# no return
}

handle_certificate() {
	local acct status order
	make_nonce || return_error 400 "badNonce" "failed to create new nonce"
	log "INFO" "certificate: process"
	# abusing the acct response
	acct=$(verify_acct) || return_error 400 "${acct}"
	order=$(extract_id)
	if [ -z "$order" ]; then
		log "ERROR" "certificate: no order specified"
		return_error 400 "malformed" "no order in url"
		# no return
	fi
	log "INFO" "certificate: handling order ${order}"
	if [ -f "${ACME_DIR}/certs/${order}.pem" ]; then
#NOTE: CAT to _BODY eats the newline and borks the cert. so replicate the
# return_success() function.
		set_header "Content-Type: application/pem-certificate-chain"
		set_header "Link: <${ISSUER_URL}/directory>;rel=\"index\""
		# return the HTTP status back to CGI interperter
		echo "Status: 200 $(hc_string "${_hc}")"
		# output the headers
		for _h in "${_HEADERS[@]}"; do
			echo "${_h}"
		done
		echo
		# output a body if it exists
		${CAT} "${ACME_DIR}/certs/${order}.pem" | ${SED} -n '/^-----/,/^-----/p'
		clean_content
		log "INFO" "certificate: success"
		exit 0
	else
		log "INFO" "certificate: invalid certificate request"
		return_error 401 "invalidChallenge" "cannot find requested order"
		# no return
	fi
	log "INFO" "certificate: success"
	return_result 200 "OK"
	# no return
}

handle_revoke() {
	local acct status _ret
	make_nonce || return_error 400 "badNonce" "failed to create new nonce"
	log "INFO" "revoke process"
	acct=$(verify_acct) || return_error 400 "${acct}"
	_ret=$(process_revoke "${acct}")
	case "$?" in
		1) #alreadyRevoked
			log "ERROR" "revoke: already revoked"
			return_error 401 "alreadyRevoked" "${_ret}"
			# no return
			;;
		2) #not found
			log "ERROR" "revoke: certificate not found"
			return_error 401 "badCertificate" "${_ret}"
			# no return
			;;
		3) # other
			log "ERROR" "revoke: error ${_ret}"
			return_error 401 "malformed" "${_ret}"
			# no return
			;;
	esac

	_BODY=""
	log "INFO" "revoke success"
	return_result 200 "OK"
	# no return
}

### --- MAIN ---
conf=$(find_conf)
if [ -z "${conf}" ]; then
	echo "Status: 500 config not found"
	exit 1
else
	. "${conf}"
fi

# --- CONFIG ---
# no defaults
ISSUER_DOMAIN=${ISSUER_DOMAIN:-""}
ISSUER_EMAIL=${ISSUER_EMAIL:-""}
ISSUER_URL=${ISSUER_URL:-"https://${ISSUER_DOMAIN}/acme"}
# has defaults
LOG_FILE=${LOG_FILE:-"/logs/acme.log"}
ACME_DIR=${ACME_DIR:-"/acme"}
MAX_CERT_DAYS=${MAX_CERT_DAYS:-90}
PERMIT_RESERVED_TLDS=${PERMIT_RESERVED_TLDS:-0}
NONCE_EXPIRE=${NONCE_EXPIRE:-300}
CLIENT_RETRY=${CLIENT_RETRY:-5}
ORDER_EXPIRE=${ORDER_EXPIRE:-300}
VERIFY_TIMEOUT=${VERIFY_TIMEOUT:-1}
VERIFY_RETRIES=${VERIFY_RETRIES:-1}
VERIFY_DELAY=${VERIFY_DELAY:-1}
CA_HELPER=${CA_HELPER:-"/cgi-bin/ACME_helper.sh"}
DEBUG=${DEBUG:-0}
DEVNUL=${DEVNUL:-"/dev/null"}
# default max size is 64k...
MAX_REQUEST_SIZE=${MAX_REQUEST_SIZE:-65535}
#INVALID_TARGETS="127.0.0.1 localhost 169.254.169.254"
# disabled for now... maybe handle in future.
PERMIT_IDNA=0
#NOTE: allow for updates from config???
RESERVED_TLDS="local|internal|localhost|test|example|invalid|onion|corp|home|lan|intranet"

if [ -z "${ISSUER_DOMAIN}" -o -z "${ISSUER_EMAIL}" ]; then
	log "ERROR" "incomplete config"
	echo "Status: 500 incomplete config"
	exit 1
fi

# If HTTP_HOST is set, build the URL from it as it will
# handle any name:port.  This allows for loadbalancing
# and hosting on different port than 443
if [ -n "${HTTP_HOST}" ]; then
	ISSUER_URL="https://${HTTP_HOST}/acme"
fi
# calculate MAX_CERT_TIME in seconds
MAX_CERT_TIME=$((MAX_CERT_DAYS*86400))

# send all stderr to DEVNUL file
exec 2>"${DEVNUL}"

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

# check dir structure
check_dirs "${ACME_DIR}"
if [ $? -ne 0 ]; then
	log "ERROR" "error validating directories"
	log_debug "one or more directories missing in ${ACME_DIR}"
	return_error 503 "serverInternal" "server failed internal checks"
	# no return
fi

## request must use HTTPS
if [ -z "$HTTPS" -o "$HTTPS" != "on" ]; then
	log "ERROR" "https not used"
	log_debug "HTTPS not used: '$HTTPS'"
	return_error 400 "malformed" "HTTPS must be used"
	# no return
fi
# rfc 8555 6.1 states that useragent MUST be sent
if [ -z "$HTTP_USER_AGENT" ]; then
	log "ERROR" "User agent not specified"
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
		# no return
        ;;
	*"/finalize"*)
		check_post_as_get || return_error 400 "malformed" "request expected POST-as-GET"
		check_url "finalize" || return_error 400 "malformed" "url doesn't match request"
		check_nonce || return_error 400 "badNonce" "Nonce could not be found or had expired"
		validate_jws || return_error 400 "badPublicKey" "JWS could not be verified"
        handle_finalize
		# no return
        ;;
	*"/certificate"*)
		check_post_as_get || return_error 400 "malformed" "request expected POST-as-GET"
		check_url "certificate" || return_error 400 "malformed" "url doesn't match request"
		check_nonce || return_error 400 "badNonce" "Nonce could not be found or had expired"
		validate_jws || return_error 400 "badPublicKey" "JWS could not be verified"
        handle_certificate
		# no return
        ;;
	*"/revoke"*)
		check_post_as_get || return_error 400 "malformed" "request expected POST-as-GET"
		check_url "revoke" || return_error 400 "malformed" "url doesn't match request"
		check_nonce || return_error 400 "badNonce" "Nonce could not be found or had expired"
		validate_jws || return_error 400 "badPublicKey" "JWS could not be verified"
		handle_revoke
		# no return
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


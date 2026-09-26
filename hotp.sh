#!/bin/ksh

# This script generates the HOTP decimal in accordance with RFC 4226.
# If the counter is now()/30 it will generate an TOTP decimal in
# accordance with RFC 6238.

# BSD 2-Clause License
# 
# Copyright (c) 2026, Michael Graves
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
# 
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
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

CAT=$(command -v cat)
AWK=$(command -v awk)
SED=$(command -v sed)
OSSL=$(command -v openssl)
GREP=$(command -v grep)
PRINTF=$(command -v printf)

set -e

b32tohex() {
	local _b32 _h
	if [ $# -eq 0 ]; then
		_b32=$(${CAT})
	else
		_b32=$1
	fi
	[ -z "${_b32}" ] && return
	_h=$(${AWK} -v s="${_b32}" 'BEGIN {
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    for (i = 0; i < 32; i++) map[substr(alphabet, i + 1, 1)] = i
    s = toupper(s)
    gsub(/=/, "", s)
    bits = ""
    for (i = 1; i <= length(s); i++) {
        char = substr(s, i, 1)
        if (!(char in map)) continue
        val = map[char]
        b = ""
        for (j = 4; j >= 0; j--) {
            b = b (int(val / (2^j)) % 2)
        }
        bits = bits b
    }
    hex = ""
    for (i = 1; i + 7 <= length(bits); i += 8) {
        byte_bits = substr(bits, i, 8)
        v = 0
        for (j = 1; j <= 8; j++) {
            v = v * 2 + substr(byte_bits, j, 1)
        }
        hex = hex sprintf("%02x", v)
    }
    print hex
}')
	echo "${_h}"
}

hextodec() {
	local _h _d
	if [ $# -eq 0 ]; then
		_h=$(${CAT})
	else
		_h=$1
	fi
	[ -z "${_h}" ] && return
	_d=$(${AWK} -v hmac="${_h}" '
function hex2dec(h, i, c, v) {
    h = tolower(h)
    v = 0
    for (i = 1; i <= length(h); i++) {
        c = index("0123456789abcdef", substr(h, i, 1)) - 1
        v = v * 16 + c
    }
    return v
}
BEGIN {
    # Last nibble defines offset
    last_char = substr(hmac, length(hmac), 1)
    offset = hex2dec(last_char)
    # Extract 4-byte segment (8 hex chars) at offset
    sub_hex = substr(hmac, (offset * 2) + 1, 8)
    # Mask off MSB (31-bit unsigned integer)
    val = hex2dec(sub_hex) % 2147483648
    # Extract 6-digit code
    code = val % 1000000
    printf "%06d\n", code
}')
	echo "${_d}"
}



if [ $# -lt 2 ]; then
	echo "error: missing argument" >&2
	echo "${0%%*/} <secret> <counter>" >&2
	exit 1
fi
secret=$1
counter=$2

# Validate counter is a non-negative integer
if ! echo "${counter}" | ${GREP} -qE '^[0-9]+$'; then
	echo "error: counter must be a non-negative integer" >&2
	exit 1
fi

# decode the base32 secret into hex
secret_h=$(b32tohex "${secret}")
if [ -z "${secret_h}" ]; then
	echo "error: invalid base32 secret" >&2
	exit 1
fi

# format the counter as hex
counter_h=$(${PRINTF} "%016x" "${counter}" | ${SED} 's/../\\x&/g')

# generate the hmac-sha1
hmac_h=$(${PRINTF} "${counter_h}" | ${OSSL} dgst -sha1 -mac HMAC -macopt "hexkey:${secret_h}" 2>/dev/null | ${AWK} '{print $NF}')
if [ -z "${hmac_h}" ]; then
    echo "error: failed to generate HMAC" >&2
    exit 1
fi

# convert hmac to decimal and output
hextodec "${hmac_h}"

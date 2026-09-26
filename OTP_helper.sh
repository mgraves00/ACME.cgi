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

CUT=$(command -v cut)
GREP=$(command -v grep)
SED=$(command -v sed)
CAT=$(command -v cat)
UNAME=$(command -v uname)
DATE=$(command -v date)

PROG_NAME=${0##*/}
DEVNUL=${DEVNUL:-"/dev/null"}
LOCKF="/tmp/otp_helper.lock"
LOCK_WAIT=5
LOCK_TMOUT=0

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

find_conf() {
	local _f
	for _f in "/etc/OTP_helper.conf" "/var/www/etc/OTP_helper.conf" "/usr/local/etc/OTP_helper.conf" "/app/config/OTP_helper.conf" "./OTP_helper.conf"; do
		if [ -f "${_f}" ]; then
			echo ${_f}
			return
		fi
	done
	echo ""
}

cleanup() {
	# force remove the LOCKF
	[ -f "${LOCKF}" ] && rm -f "${LOCKF}"
}

lock_alrm() {
	LOCK_TMOUT=1
}

wait_lock() {
#	echo "wait_lock: enter" >&2
	_pid=$$
	LOCK_TMOUT=0
#	echo "wait_lock: my id ${_pid}" >&2
	(
		sleep ${LOCK_WAIT:-10}
		kill -ALRM ${_pid} 2>/dev/null
	) >/dev/null 2>&1 &
	_cpid=$!
	trap lock_alrm ALRM
#	echo "wait_lock: wait for alarm or lockfile ${_cpid}" >&2
	while [ $LOCK_TMOUT -eq 0 -a -f "${LOCKF}" ]; do
#		echo "wait_lock: looping" >&2
		sleep .5
	done
	# reset alarm signal
	trap - ALRM
	if [ $LOCK_TMOUT -eq 0 ]; then
		echo -n "$_pid" > ${LOCKF}
#		echo "wait_lock: lock free" >&2
		# tell alarm to exit
#		echo "wait_lock: send EXIT to ${_cpid}" >&2
		kill -KILL ${_cpid} 2>/dev/null
		# wait for child
		wait ${_cpid} 2>/dev/null
	else
		# alarm fired
#		echo "wait_lock: alarm fired" >&2
		return 1
	fi
#	echo "wait_lock: return 0" >&2
	return 0
}

clear_lock() {
	_pid=$$
	# no lock file found
	[ ! -f "${LOCKF}" ] && return 1
	lpid=$(${CAT} "${LOCKF}")
	if [ "${_pid}" != "${lpid}" ]; then
		# we dont hold the lock
		return 2
	fi
	# looks good... do delete
	rm -f "${LOCKF}" >"${DEVNUL}" 2>&1
	return 0
}

get_counter() {
	local _req=$1
	[ -z "${_req}" ] && return 1
	if [ ! -f "${SECRETS_FILE}" ]; then
		echo "no secrets file found"
		return 1
	fi
#	echo "get_counter: getting lock" >&2
	wait_lock
#	echo "get_counter: got lock" >&2
	if [ $? -ne 0 ]; then
		echo "getting lock file"
		return 1
	fi
	_v=$(${GREP} -E "^${_req}" "${SECRETS_FILE}" | ${SED} '1q')
	echo "v=${_v}" >&2
	if [ -z "${_v}" ]; then
		echo "requestor not found"
		clear_lock
		return 1
	fi
#	echo "get_counter: clearing lock" >&2
	clear_lock
#	echo "get_counter: cleared ock" >&2
	_c=$(echo "${_v}" | ${CUT} -f3 -d:)
	echo "${_c}"
	return 0
}

get_secret() {
#	echo "get_secert: enter" >&2
	local _req=$1
	[ -z "${_req}" ] && return 1
	if [ ! -f "${SECRETS_FILE}" ]; then
		echo "no secrets file found"
		return 1
	fi
	wait_lock
	if [ $? -ne 0 ]; then
		echo "error getting lock file"
		return 1
	fi
	_v=$(${GREP} -E "^${_req}" "${SECRETS_FILE}" | ${SED} '1q')
	if [ -z "${_v}" ]; then
#		echo "get_secert: return 1" >&2
		echo "error requestor not found"
		clear_lock
		return 1
	fi
	clear_lock
	_c=$(echo "${_v}" | ${CUT} -f2 -d:)
	echo "${_c}"
#	echo "get_secert: return 0" >&2
	return 0
}

set_counter() {
	local _req=$1
	local _cnt=$2
	[ -z "${_req}" ] && return 1
	[ -z "${_cnt}" ] && return 1
	if [ ! -f "${SECRETS_FILE}" ]; then
		echo "no secrets file found"
		return 1
	fi
	wait_lock
	if [ $? -ne 0 ]; then
		echo "error getting lock file"
		return 1
	fi
	_v=$(${GREP} -E "^${_req}" "${SECRETS_FILE}" | ${SED} '1q')
	if [ -z "${_v}" ]; then
		echo "error requestor not found"
		clear_lock
		return 1
	fi
	_r=$(echo "${_v}" | ${CUT} -f1 -d:)
	_s=$(echo "${_v}" | ${CUT} -f2 -d:)
	${SED} -i -r "s/^${_r}:${_s}:.*/${_r}:${_s}:${_cnt}/" "${SECRETS_FILE}" >${DEVNUL} 2>&1
	if [ $? -ne 0 ]; then
		echo "error updating the counter"
		clear_lock	
		return 1
	fi
	clear_lock
	return 0
}


### MAIN
conf=$(find_conf)
if [ -z "${conf}" ]; then
	echo "Status: 500 config not found"
	exit 1
else
	. "${conf}"
fi

if [ $# -lt 1 ]; then
	echo "${PROG_NAME} <otp_type> <requestor> <otp> [counter]" >&2
	echo "OTP Types:" >&2
	echo "  hotp - HMAC one time password. requires counter" >&2
	echo "  totp - Temproal one time password" >&2
	exit 1
fi

# clean up if we get a signal
trap cleanup HUP INT QUIT TERM TSTP EXIT

otp_type=$1
requestor=$2
otp=$3
counter=$4
secret=$(get_secret "${requestor}")
if [ $? -ne 0 ]; then
	echo "error"
	echo "getting requestor: ${secret}" >&2
	exit 1
fi

case "$otp_type" in
	"hotp")
		last_counter=$(get_counter "${requestor}")
		if [ $? -ne 0 ]; then
			echo "error"
			echo "looking up requestor: ${last_counter}" >&2
			exit 1
		fi
		echo "last_counter = ${last_counter}" >"${DEVNUL}"
		if [ "${counter}" -lt "${last_counter}" ]; then
			# counter went backwards... replay attach
			echo "error"
			echo "counter went backwards" >&2
			exit 1
		fi
		_d=$(${OTP_PROG} "${secret}" "${counter}")
		if [ "${_d}" != "${otp}" ]; then
			# doesn´t match
			echo "error"
			echo "no match" >&2
			return 1
		fi
		x=$(set_counter "${requestor}" $((counter + 1)))
		if [ $? -ne 0 ]; then
			echo "error"
			echo "error incrementing counter: ${x}" >&2
			return 1
		fi
		;;
	"totp")
		_n=$(now_epoch)
		# accept values +/- 30 seconds of now to account for clock skews
		_c[0]=$((_n / 30))
		_c[1]=$((_n / 30 - 1))
		_c[2]=$((_n / 30 + 1))
		_ok=0
		# loop thru values and check.
		for _t in ${_c}; do
			_d=$(${OTP_PROG} "${secret}" "${_t}")
			[ "${_d}" == "${otp}" ] && break
			_ok=$((_ok+1))
		done
		if [ ${_ok} -eq 3 ]; then
			echo "error"
			echo "no match" >&2
			return 1
		fi
		# We dont check the counter goes backwards, but it really doesn´
		# matter because we only accept counter values within +/- 30 seconds
		# of now.  So record the last "match" time.
		x=$(set_counter "${requestor}" $((_c[${_ok}] + 1)))
		if [ $? -ne 0 ]; then
			echo "error"
			echo "error incrementing counter: ${x}" >&2
			return 1
		fi
		;;
	*)
		echo "error"
		echo "unknown type: $otp_type" >&2
		exit 1
		;;
esac

echo "success"
cleanup
exit 0


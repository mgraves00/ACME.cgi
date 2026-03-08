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

LS=$(which ls)
JQ=$(which jq)
RM=$(which rm)
DATE=$(which date)
CAT=$(which cat)

find_conf() {
    local _f
    for _f in "/etc/ACME.conf" "/app/config/ACME.conf" ".env"; do
        if [ -f "${_f}" ]; then
            echo ${_f}
            return
        fi
    done
    echo ""
}

rfc3339_to_epoch() {
	if [ -z "$1" ]; then
		echo "0"
	fi
	local _e=`${DATE} -j -f "%Y-%m-%dT%H:%M:%S%z" +"%s" "$1"`
	if [ -z "${_e}" ]; then
		echo "0"
	fi
	echo "${_e}"
}

NOW=$(${DATE} -j +"%s")

conf=`find_conf`
if [ -z "$conf" ]; then
	echo "cannot find conf file"
	exit 1
fi

ACME_DIR=${ACME_DIR:-"/acme"}

# test to see if ACME_DIR exists
if [ -z "${ACME_DIR}" -o ! -d "${ACME_DIR}" ]; then
	echo "cannot find ${ACME_DIR}"
	exit 1
fi

# cleanup old nonces
for _n in `${LS} ${ACME_DIR}/nonce`; do
	_nt=`${CAT} ${ACME_DIR}/nonce/${_n}`
	if [ ${_nt} -lt ${NOW} ]; then
		${RM} -f ${ACME_DIR}/nonce/${_n}
	fi
done

# clean up old orders
echo "cleaning up orders..."
for _o in `${LS} ${ACME_DIR}/orders`; do
	_s=`${CAT} ${ACME_DIR}/orders/${_o} | ${JQ} -cr '.status'`
	case ${_s} in
		invalid)
			# invalid... delete it
			echo "removing invalid order ${ACME_DIR}/orders/${_o}"
			${RM} -f ${ACME_DIR}/orders/${_o}
			;;
		*)
			# delete expired orders
			_e=`${CAT} ${ACME_DIR}/orders/${_o} | ${JQ} -cr '.expires'`
			_et=`rfc3339_to_epoch "${_e}"`
			if [ ${NOW} -gt ${_et} ]; then
				echo "removing expired order ${ACME_DIR}/orders/${_o}"
				${RM} -f ${ACME_DIR}/orders/${_o}
			fi
			;;
	esac
done

# clean up old challenges
echo "cleaning up challenges..."
for _o in `${LS} ${ACME_DIR}/challenges`; do
	_s=`${CAT} ${ACME_DIR}/challenges/${_o} | ${JQ} -cr '.status'`
	case ${_s} in
		invalid)
			# invalid... delete it
			echo "removing invalid challenge ${ACME_DIR}/challenges/${_o}"
			${RM} -f ${ACME_DIR}/challenges/${_o}
			;;
		*)
			# delete expired orders
			_e=`${CAT} ${ACME_DIR}/challenges/${_o} | ${JQ} -cr '.expires'`
			_et=`rfc3339_to_epoch "${_e}"`
			if [ ${NOW} -gt ${_et} ]; then
				echo "removing expired challenge ${ACME_DIR}/challenges/${_o}"
				${RM} -f ${ACME_DIR}/challenges/${_o}
			fi
			;;
	esac
done

# look for deactivated accounts
echo "cleaning up accounts..."
for _a in `${LS} ${ACME_DIR}/accts`; do
	
	if [ ${_a%%.pem} != ${_a} ]; then
		# skip PEM files
		continue
	fi
	status=$(cat ${ACME_DIR}/accts/${_a} | ${JQ} -cr '.status')
	case ${status} in
		deactivated)
			# delete all requests and certs
			echo "removing certs for deactivated account ${ACME_DIR}/certs/${_a}"
			${RM} -f ${ACME_DIR}/certs/${_a}_*.pem
			${RM} -f ${ACME_DIR}/certs/${_a}_*.req
			# delete the account
			echo "removing deactivated account ${ACME_DIR}/account/${_a}"
			${RM} -f ${ACME_DIR}/accts/${_a}.pem
			${RM} -f ${ACME_DIR}/accts/${_a}
			;;
	esac
done


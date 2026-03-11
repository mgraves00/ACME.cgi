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

# Generate a new CRL and update the HTML environment

if [ -z "${CA_NAME}" ]; then
	echo "CA_NAME not specified"
	exit 1
fi

pca ${CA_NAME} create crl
if [ $? -ne 0 ]; then
	echo "error creating CRL"
	exit 1
fi

pca ${CA_NAME} export html -file /app/ca.tgz -overwrite
if [ $? -ne 0 ]; then
	echo "error creating HTML archive"
	exit 1
fi
tar -vzx --no-same-permissions -f /app/ca.tgz -C /app/data
if [ $? -ne 0 ]; then
	echo "error extracting HTML archive"
	exit 1
fi
cp index.html.dist /app/html/index.html
if [ $? -ne 0 ]; then
	echo "error copying html file"
	exit 1
fi
sed -i "s,@@CA_NAME@@,${CA_NAME}," /app/html/index.html
if [ $? -ne 0 ]; then
	echo "error setting CA_NAME"
	exit 1
fi
exit 0

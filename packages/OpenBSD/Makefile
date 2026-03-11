# $OpenBSD$
#
COMMENT 	= rfc8555 compliant certificate registration authority
VERSION  	= 0.1
DISTNAME	= ACME.cgi-${VERSION}
CATEGORIES	= security
HOMEPAGE	= https://github.com/mgraves00/ACME.cgi
MAINTAINER	= Michael Graves <mg@brainfat.net>

# BSD 2 Clause
PERMIT_PACKAGE = Yes
PERMIT_DISTFILES = Yes

GH_ACCOUNT 	= mgraves00
GH_PROJECT 	= ACME.cgi
GH_TAGNAME 	= v${VERSION}
#GH_COMMIT	= 3fce5176be51c7342e77b646e0274c2fa770f1ca

CONFIG_STYLE = none
NO_BUILD	= Yes
NO_TEST		= Yes
PKG_ARCH	= *

RUN_DEPENDS	= textproc/jq net/curl security/pca

PREFIX =	${VARBASE}/www
SUBST_VARS = VARBASE

do-install:
	${INSTALL_SCRIPT_DIR} ${PREFIX}/cgi-bin
	${INSTALL_SCRIPT} ${WRKSRC}/ACME.cgi ${PREFIX}/cgi-bin/
	${INSTALL_SCRIPT} ${WRKSRC}/ACME_helper.sh ${PREFIX}/cgi-bin/
	${INSTALL_SCRIPT} ${WRKSRC}/ACME_cleaner.sh ${PREFIX}/cgi-bin/
	${INSTALL_DATA_DIR} ${PREFIX}/etc
	${INSTALL_DATA} ${WRKSRC}/ACME.conf ${PREFIX}/etc/ACME.conf.example
	${INSTALL_DATA} ${WRKSRC}/ACME_helper.conf ${PREFIX}/etc/ACME_helper.conf.example

.include <bsd.port.mk>


#
NAME = acmecgi
VERSION = 0.4

FILES = ACME.cgi ACME_helper.sh ACME_cleaner.sh
PARENT_DIR = ../..

build: copy_files Dockerfile
	docker build --tag ${NAME}:${VERSION} .

test:
	docker run -it --rm --env-file .env -p "10443:8443/tcp" -v "./config:/app/config" -v "./data:/app/data" -v "./logs:/app/logs" --entrypoint=/bin/sh ${NAME}:${VERSION} 

connect:
	docker exec -it `docker ps | grep ${NAME} | cut -f1 -d" "` /bin/ash

run:
	docker run -it --rm --env-file .env -p "10443:8443/tcp" -v "./config:/app/config" -v "./data:/app/data" -v "./logs:/app/logs" ${NAME}:${VERSION} 

clean:
	docker image rm ${NAME}:${VERSION}

copy_files:
	[[ -d ./tmp ]] || mkdir ./tmp; \
	for f in $(FILES); do \
		cp $(PARENT_DIR)/$$f ./tmp/$$f; \
	done

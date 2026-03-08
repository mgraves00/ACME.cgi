# Docker

## Docker build

To build a docker container run
'''
docker build --tag acmecgi:latest .
'''

To run the docker

'''
mkdir ./config
mkdir ./data
mkdir ./logs
docker run -d --rm --env-file .env -p "8080:8080/tcp" -p "9995:9995/udp" -v "./config:/app/config" -v "./data:/app/pca" -v "./logs:/app/logs" acmecgi:latest
'''

## Docker compose

To run under docker compose, update the env.example file and copy to .env.  Then start with docker compose

'''
docker-compose up -d
'''

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
docker run -d --rm --env-file .env -p "8443:8443/tcp" -v "./config:/app/config" -v "./data:/app/data" -v "./logs:/app/logs" acmecgi:latest
'''

## Docker compose

To run under docker compose, update the env.example file and copy to .env.  Then start with docker compose

'''
docker-compose up -d
'''

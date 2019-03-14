#!/bin/bash
CONTAINER_IMAGE=$1
if [ `docker ps | grep searchapi | wc -l` -gt 0 ]; then
	docker stop searchapi
fi
docker container prune -f 
docker run -d -p 8082:8082 --name=searchapi $CONTAINER_IMAGE
#!/bin/bash
CONTAINER_IMAGE=$1
if [ `docker ps | grep dataapi | wc -l` -gt 0 ]; then
	docker stop dataapi
fi
docker container prune -f 
docker run -d --rm -p 8082:8082  --name=dataapi $CONTAINER_IMAGE
SHELL := /bin/bash
-include .env
export $(shell sed 's/=.*//' .env)
.ONESHELL: # Applies to every targets in the file!
.PHONY: help

help: ## This help.
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.DEFAULT_GOAL := help

setup:
	docker volume create --name=linode-slack-db

build: ## docker-compose build
	docker-compose build

buildnc: ## docker-compose build --no-cache
	docker-compose build --no-cache

rebuild: down build ## alias for down && build

docker-clean: ## quick docker environment cleanup
	docker rmi $(docker images -qaf "dangling=true")
	yes | docker system prune
	sudo service docker restart

docker-purge: ## thorough docker environment cleanup
	docker rmi $(docker images -qa)
	yes | docker system prune
	sudo service docker stop
	sudo rm -rf /tmp/docker.backup/
	sudo cp -Pfr /var/lib/docker /tmp/docker.backup
	sudo rm -rf /var/lib/docker
	sudo service docker start

up: ## Starts the container
	docker-compose up -d

down: ## Bring down all running containers
	@docker-compose down --remove-orphans

restart: down up ## alias for down && up

push: ## Push to dockerhub
	@echo ${DOCKERHUB_TOKEN} | docker login --password-stdin -u ${GITLAB_USER}
	docker-compose push linode-slackbot

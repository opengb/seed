.PHONY: docker
docker:
	docker build -t opengb/seed:no-merge .
	# docker build --no-cache -t opengb/seed:cc6ee50b .

test: testpy testjs

testpy:
	python manage.py test --settings=config.settings.test

testjs:
	open http://localhost:9000/app/angular_js_tests/

lint: lintpy lintjs

lintjs:
	jshint seed/static/seed/js
lintpy:
	tox -e flake8

coverage:
	coverage run manage.py test --settings=config.settings.test
	coverage report --fail-under=83

tags:
	ctags -R --fields=+l --languages=python --python-kinds=-iv api seed

.PHONY: tags

build:
	# docker build --tag ryanmccuaig/seed:skeleton-base .
	docker build -f Dockerfile-web --tag ryanmccuaig/seed:skeleton-web  .
	docker build -f Dockerfile-celery --tag ryanmccuaig/seed:skeleton-celery .

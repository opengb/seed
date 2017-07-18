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

i18n: i18n_js i18n_py

i18n_js:
	grunt i18nextract

PY_SRC=$(shell find seed -name "*.py")

i18n_py: locale/fr_CA/LC_MESSAGES/django.po
	python manage.py compilemessages --locale=fr_CA

locale/fr_CA/LC_MESSAGES/django.po: $(PY_SRC)
	python manage.py makemessages --locale=fr_CA --ignore venv --ignore node_modules --ignore seed/static/vendor

.PHONY: i18n_js i18n_py

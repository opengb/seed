test: testpy testjs

testpy:
	python manage.py test --settings=config.settings.test

lint: lintpy lintjs 

lintjs:
	jshint seed/static/seed/js
lintpy:
	tox -e flake8

coverage:
	coverage run manage.py test --settings=config.settings.test
	coverage report --fail-under=83

tags:
	ctags -R --fields=+l --languages=python --python-kinds=-iv seed

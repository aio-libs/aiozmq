# Some simple testing tasks (sorry, UNIX only).

PYTHON=python3.3

FILTER=

doc:
	cd docs && make html
	echo "open file://`pwd`/docs/_build/html/index.html"

pep:
	pep8 aiozmq examples

flake:
	pyflakes3 .

test:
	$(PYTHON) runtests.py $(FILTER)

vtest:
	$(PYTHON) runtests.py -v $(FILTER)

testloop:
	$(PYTHON) runtests.py --forever $(FILTER)

cov cover coverage:
	$(PYTHON) runtests.py --coverage $(FILTER)

clean:
	rm -rf `find . -name __pycache__`
	rm -f `find . -type f -name '*.py[co]' `
	rm -f `find . -type f -name '*~' `
	rm -f `find . -type f -name '.*~' `
	rm -f `find . -type f -name '@*' `
	rm -f `find . -type f -name '#*#' `
	rm -f `find . -type f -name '*.orig' `
	rm -f `find . -type f -name '*.rej' `
	rm -f .coverage
	rm -rf coverage

.PHONY: all pep test vtest testloop cov clean

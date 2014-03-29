# Some simple testing tasks (sorry, UNIX only).

PYTHON=python3.3

FILTER=

doc:
	cd docs && make html
	echo "open file://`pwd`/docs/_build/html/index.html"

pep:
	pep8 aiozmq examples tests

flake:
	pyflakes3 .

test: pep flake
	$(PYTHON) runtests.py $(FILTER)

vtest: pep flake
	$(PYTHON) runtests.py -v $(FILTER)

testloop: pep flake
	$(PYTHON) runtests.py --forever $(FILTER)

cov cover coverage: pep flake
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

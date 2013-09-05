# Some simple testing tasks (sorry, UNIX only).

PYTHON=python3.3
NOSE=../../bin/nosetests
FLAKE=flake8
FLAGS=


pep:
	$(FLAKE) ./

test:
	$(NOSE) -s $(FLAGS)

vtest:
	$(NOSE) -s -v $(FLAGS)

testloop:
	while sleep 1; do $(PYTHON) runtests.py $(FLAGS); done

cov cover coverage:
	$(NOSE) -s --with-cover --cover-html --cover-html-dir ./coverage $(FLAGS)
	echo "open file://`pwd`/coverage/index.html"

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

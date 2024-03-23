Building
========

Documentation
-------------
This documentation is built using Sphinx. To build the documentation, you will
need to have Sphinx installed. You can build as follows, and the HTML
documentation will be in the `docs/_build` directory.

.. code-block:: bash

	source venv/bin/activate
	pip3 install sphinx sphinx_rtd_theme
	sphinx-build docs docs/_build

Package
-------
Python wheels can be built using the following commands, and the wheel will be
in the `dist` directory.

.. code-block:: bash

	source venv/bin/activate
	python3 -m pip install --upgrade build twine
	python3 -m build
	python3 -m twine upload dist/*

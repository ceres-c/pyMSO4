# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'pyMSO4'
copyright = '2024, ceres-c'
author = 'Federico Cerutti / ceres-c'
release = '0.1'

import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.absolute()))

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
	'sphinx.ext.autodoc',
	'sphinx.ext.viewcode',
	'sphinx.ext.napoleon',
    "sphinx.ext.intersphinx",
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

autodoc_default_options = {
    'special-members': '__init__',
	'member-order': 'bysource',
}

intersphinx_mapping = {
    "pyvisa": ("https://pyvisa.readthedocs.io/en/latest/", None),
}

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']

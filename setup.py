from setuptools import setup, find_packages

setup(
    name='pankegg',
    version='1.0',
    packages=find_packages(include=['lib', 'lib.*']),
    include_package_data=True,
    py_modules=['pankegg_make_db', 'pankegg_app'],
    install_requires=[
        'flask',
        'pandas',
        'numpy',
        'scikit-learn',
        'scipy',
        'jinja2',
        'setuptools',
        'click',
        'importlib-metadata; python_version<"3.8"',
        'pytest==8.4.0',
    ],
    entry_points={
        'console_scripts': [
            'pankegg_app=pankegg_app:start_server',
            'pankegg_make_db=pankegg_make_db:main',
        ],
    },
    author='Arnaud Vanbelle & Renaud Van Damme',
    author_email='renaud.van.damme@slu.se',
    description='Flask App for PanKEGG',
    url='https://github.com/RVanDamme/PANKEGG',
)

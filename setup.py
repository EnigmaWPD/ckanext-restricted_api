from setuptools import setup, find_packages

# This is a custom setup.py file, which the upstream extension does not possess

version = '1.0.0'

setup(
    name='ckanext-restricted_api',
    version=version,
    description='API logic for restricting access to dataset resources',
    long_description='',
    # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[],
    keywords='',
    author='Sam Woodcock',
    author_email='sam.woodcock@protonmail.com',
    url='https://github.com/EnigmaWPD/ckanext-restricted_api/tree/1.0.0-main',
    license='',
    packages=find_packages(exclude=['contrib', 'docs', 'tests*']),
    namespace_packages=['ckanext'],
    include_package_data=True,
    package_data={},
    zip_safe=False,
    install_requires=[],
    dependency_links=[],
    entry_points="""
    [ckan.plugins]
    restricted_api=ckanext.restricted_api.plugin:RestrictedAPIPlugin
    """,
)

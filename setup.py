"""Setup configuration for octopus package"""
from setuptools import setup, find_packages
from pathlib import Path

# Read the contents of README.md
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()

setup(
    name='octopus',
    version='0.1.0',
    author='EmpowerSaves',
    author_email='dev@empowersaves.com',
    description='EmailOctopus Campaign Analytics & Reporting Dashboard',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/empowersaves/octopus',
    packages=find_packages(include=['app', 'app.*', 'src', 'src.*']),
    include_package_data=True,
    python_requires='>=3.9',
    install_requires=[
        'Flask>=3.0.0',
        'Werkzeug>=3.0.1',
        'Flask-SQLAlchemy>=3.1.1',
        'Flask-Login>=0.6.3',
        'Flask-WTF>=1.2.1',
        'email-validator>=2.1.0',
        'python-dotenv>=1.0.0',
        'requests>=2.31.0',
        'numpy>=1.26.3',
    ],
    extras_require={
        'dev': [
            'pytest>=7.4.0',
            'pytest-cov>=4.1.0',
            'black>=23.0.0',
            'flake8>=6.1.0',
            'mypy>=1.5.0',
        ],
        'mongodb': [
            'pymongo>=4.6.1',
            'mongoengine>=0.27.0',
        ],
        'reporting': [
            'plotly>=5.18.0',
            'ReportLab>=4.0.7',
            'APScheduler>=3.10.4',
        ],
    },
    entry_points={
        'console_scripts': [
            'octopus=app.cli:main',
            'octopus-create-user=scripts.create_user:main',
        ],
    },
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Internet :: WWW/HTTP :: WSGI :: Application',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Framework :: Flask',
    ],
    keywords='emailoctopus campaign analytics reporting dashboard',
    project_urls={
        'Source': 'https://github.com/empowersaves/octopus',
        'Tracker': 'https://github.com/empowersaves/octopus/issues',
    },
)

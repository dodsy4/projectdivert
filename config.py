import os
SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(32))
# Grabs the folder where the script runs.
basedir = os.path.abspath(os.path.dirname(__file__))

# Enable debug mode.
DEBUG = os.environ.get('FLASK_DEBUG', '0') == '1'

# Connect to the database


raw_database_url = os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(basedir, 'app.db'))
if raw_database_url.startswith('postgres://'):
    raw_database_url = raw_database_url.replace('postgres://', 'postgresql://', 1)

SQLALCHEMY_DATABASE_URI = raw_database_url

SQLALCHEMY_TRACK_MODIFICATIONS = False

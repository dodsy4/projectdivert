"""WSGI entry point: ``gunicorn wsgi:app``."""

from projectdivert import create_app

app = create_app()

if __name__ == '__main__':
    app.run(port=int(__import__('os').environ.get('PORT', 5000)))

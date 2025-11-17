from flask import Flask
import logging
from . import views


def _configure_logger() -> None:
    log = logging.getLogger("sensor_server")
    if not log.handlers:
        log.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(handler)


def create_app() -> Flask:
    _configure_logger()
    app = Flask(__name__)
    views.register_routes(app)
    return app


app = create_app()

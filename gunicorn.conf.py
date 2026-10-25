import os


def post_fork(server, worker):
    """Run DB init and scheduler startup inside each worker after fork.
    start_scheduler uses an fcntl exclusive lock, so only one worker
    actually starts the scheduler — the others skip silently.
    """
    from database import init_db
    from main import app
    from services.scheduler import start_scheduler

    with app.app_context():
        init_db()

    if os.environ.get('FLASK_TESTING') != '1':
        start_scheduler(app)

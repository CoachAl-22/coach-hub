import os
from main import app

if __name__ == '__main__':
    from database import init_db
    from services.scheduler import start_scheduler
    with app.app_context():
        init_db()
    if os.environ.get('FLASK_TESTING') != '1':
        start_scheduler(app)
    app.run(host='0.0.0.0', port=5000, debug=False)

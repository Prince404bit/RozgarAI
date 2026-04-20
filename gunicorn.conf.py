# Gunicorn config for KaamMitr
# Run: gunicorn -c gunicorn.conf.py "app:create_app()"

import multiprocessing

bind            = "0.0.0.0:5000"
workers         = 2                      # keep low for SQLite; scale up with Postgres
worker_class    = "sync"                 # sync is safest for SQLite
threads         = 2
timeout         = 60
keepalive       = 5
max_requests    = 500                    # recycle workers to avoid memory leak
max_requests_jitter = 50
accesslog       = "-"
errorlog        = "-"
loglevel        = "info"

# SQLite lock prevention: single worker or use WAL mode
# To enable WAL: run once → sqlite3 rural_employment.db "PRAGMA journal_mode=WAL;"

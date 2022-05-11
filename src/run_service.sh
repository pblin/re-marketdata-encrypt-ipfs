#/bin/bash
gunicorn3 --certfile godscoin_co.crt  --keyfile godscoin_co.key2 -b 0.0.0.0:8082 app:app


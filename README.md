# UCSD-CSE-118-Team-1
CSE 118 Final Project - Fall 2025

Server to receive sensor data from Wear OS watch and save raw JSON payloads.

Running locally
--------------

1) Create a Python environment and install requirements (runs relative to the repo root):

```bash
make install
```

2) Start the server (writes files into `./data/` relative to the repository root):

```bash
make run
```

The server listens on 0.0.0.0:5000 and exposes POST /end.

Quick test (curl)
------------------

Create a file `sample.json` with the JSON payload and then:

```bash
curl -v -X POST \
	-H "Content-Type: application/json" \
	--data-binary @sample.json \
	http://127.0.0.1:5000/end
```

After a successful POST a new file will appear in `data/`, named like:

```
session_2023-10-27_15-45-30_123456.json
```

Notes
-----
- The `data/` directory is created automatically under the repository root.
- Use `make clean` to remove captured JSON files.


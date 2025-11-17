PYTHON=python3
PIP=$(PYTHON) -m pip

.PHONY: install run clean

install:
	$(PIP) install -r requirements.txt

run:
	$(PYTHON) sensor_server.py

clean:
	rm -rf data/*.json || true

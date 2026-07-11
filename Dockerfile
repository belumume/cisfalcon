# CisFalcon web tool — the gate (TensorFlow) + parallel Claude agents + JASPAR-grounded
# motif surgery, served with FastAPI. Build context is the cisfalcon/ package dir.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 TF_CPP_MIN_LOG_LEVEL=3

WORKDIR /app

COPY webapp/backend/requirements.txt ./req.txt
RUN pip install --no-cache-dir -r req.txt

# the verified core + the fold models
COPY gate.py verifier.py ./
COPY models/ ./models/
# the web backend (app, motif surgery, static frontend, pre-fetched JASPAR PWM cache)
COPY webapp/backend/ ./webapp/backend/
# small runtime data (screenaudit result + the slim demo hero; NOT the 29MB benchmark csv)
COPY screenaudit/screenaudit_result.json ./screenaudit/screenaudit_result.json
COPY data/gosai_designed/hero.json ./data/gosai_designed/hero.json
COPY data/gosai_designed/brain_hero.json ./data/gosai_designed/brain_hero.json
COPY data/gosai_designed/batch_example.json ./data/gosai_designed/batch_example.json
# the isotonic failure-probability calibration (held-out ECE 0.0031); absent = sigmoid fallback
COPY data/calibration.csv ./data/calibration.csv

ENV CISFALCON_DIAGNOSE_CAP=200
EXPOSE 8080
WORKDIR /app/webapp/backend
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]

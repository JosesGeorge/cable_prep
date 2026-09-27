# INZORA CablePrep

Intelligent Specimen Preparation & Quality Control Platform — prototype web app.

## Stack
- **Frontend:** HTML / CSS / vanilla JS (`templates/`, `static/`), polling the backend every 500ms
- **Backend:** Python + Flask (`app.py`) — process controller, sensor simulator, adaptive cut logic, inspection logic
- **Database:** SQLite (`inzora.db`, created automatically on first run)

## Run it

```bash
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Then open **http://127.0.0.1:5000** in your browser.

## What it does
- **Control Room** — Start / Stop / Reset / E-Stop, feed speed / cut depth / force limit sliders, the FEED→STRAIGHTEN→MEASURE→CUT→PEEL→FORM→INSPECT process flow, and live sensor readouts.
- **Specimen Preparation** — cable geometry profile (with a cross-section that reacts to ovality) and the adaptive cutting closed-loop panel. Use **Simulate High-Force Event** during a run to trigger the warning → reduce-depth → resume sequence.
- **Quality & Traceability** — vision inspection results, the specimen record log (persisted in SQLite), CSV export, and the prototype status checklist.

## API
| Method | Route | Purpose |
|---|---|---|
| GET | `/api/state` | current stage, sensors, adaptive params, last inspection |
| POST | `/api/control/start` \| `stop` \| `reset` \| `estop` | machine control |
| POST | `/api/params` | update feed speed / cut depth / force limit |
| POST | `/api/spike` | trigger a simulated force spike |
| GET | `/api/specimens` | last 100 specimen records |
| GET | `/api/export` | download the specimen log as CSV |

## Next steps toward the real system
- Physical feed mechanism
- Force sensor integration
- Optical measurement hardware
- Automated cutting mechanism
- Vision camera integration (swap `run_inspection()` in `app.py` for OpenCV once a camera is wired in)

An ESP32/PLC talking to this same Flask API is the intended path to real hardware — the simulator in `app.py` is written so `update_sensors()` can be swapped for real sensor reads without touching the frontend.

import csv
import io
import random
import sqlite3
import threading
import time
from datetime import datetime

from flask import Flask, jsonify, render_template, request, send_file

app = Flask(__name__)

DB_PATH = "inzora.db"
STAGES = ["FEED", "STRAIGHTEN", "MEASURE", "CUT", "PEEL", "FORM", "INSPECT"]
STAGE_SECONDS = 1.4

lock = threading.Lock()

state = {
    "running": False,
    "stage_idx": -1,
    "status": "READY",
    "force_spike_active": False,
    "force_spike_queued": False,
    "params": {"feed_speed": 25, "cut_depth": 1.8, "force_limit": 12},
    "sensors": {
        "diameter": 8.42, "ovality": 0.12, "runout": 0.08,
        "force": 0.0, "feed": 0.0, "length": 150.0,
    },
    "last_run": {"diameter": 8.42, "depth": 1.8, "force": 0.0},
}

worker_thread = None
specimen_seq = 17


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS specimens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            specimen_id TEXT NOT NULL,
            diameter REAL, cut_depth REAL, max_force REAL,
            length REAL, result TEXT, created_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def jitter(base, amt):
    return base + (random.random() - 0.5) * amt


def update_sensors():
    p = state["params"]
    s = state["sensors"]
    s["diameter"] = round(jitter(8.42, 0.06), 2)
    s["ovality"] = round(max(0, jitter(0.12, 0.04)), 2)
    s["runout"] = round(max(0, jitter(0.08, 0.04)), 2)
    s["length"] = round(jitter(150.0, 0.6), 1)

    if state["running"] and STAGES[state["stage_idx"]] == "CUT":
        force = jitter(13.4, 0.6) if state["force_spike_active"] else jitter(8.6, 1.2)
    elif state["running"]:
        force = jitter(2.0, 1.0)
    else:
        force = 0.0
    s["force"] = round(max(0, force), 1)
    s["feed"] = round(max(0, jitter(p["feed_speed"], 1.2)) if state["running"] else 0.0, 1)

    limit = p["force_limit"]
    if s["force"] > limit:
        state["force_spike_active"] = True
        adaptive_depth = max(0.6, p["cut_depth"] - 0.4)
    else:
        if state["force_spike_active"]:
            state["force_spike_active"] = False
        adaptive_depth = p["cut_depth"]

    boundary = round(s["diameter"] * 0.685, 2)
    state["adaptive"] = {
        "boundary": boundary,
        "target_depth": p["cut_depth"],
        "adaptive_depth": round(adaptive_depth, 2),
        "limit": limit,
    }
    state["last_run"] = {"diameter": s["diameter"], "depth": adaptive_depth, "force": s["force"]}


def run_inspection():
    length = round(jitter(150, 0.6), 1)
    width = round(jitter(25, 0.4), 1)
    thickness = round(jitter(3.4, 0.15), 1)
    length_ok = abs(length - 150) < 1
    width_ok = abs(width - 25) < 0.8
    thickness_ok = abs(thickness - 3.4) < 0.3
    edge_ok = state["last_run"]["force"] < state["params"]["force_limit"] * 1.15
    surface_ok = random.random() > 0.08
    passed = length_ok and width_ok and thickness_ok and edge_ok and surface_ok

    result = {
        "length": length, "length_ok": length_ok,
        "width": width, "width_ok": width_ok,
        "thickness": thickness, "thickness_ok": thickness_ok,
        "edge_ok": edge_ok, "surface_ok": surface_ok,
        "pass": passed,
    }
    state["last_inspection"] = result
    log_specimen(state["last_run"]["diameter"], state["last_run"]["depth"],
                 state["last_run"]["force"], length, passed)
    return result


def log_specimen(diameter, depth, force, length, passed):
    global specimen_seq
    specimen_seq += 1
    specimen_id = f"CP-2026-{specimen_seq:04d}"
    created_at = datetime.now().strftime("%H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO specimens (specimen_id, diameter, cut_depth, max_force, length, result, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (specimen_id, diameter, depth, force, length, "PASS" if passed else "FAIL", created_at),
    )
    conn.commit()
    conn.close()


def process_worker():
    with lock:
        state["stage_idx"] = 0
        state["status"] = "RUNNING"
    while True:
        time.sleep(STAGE_SECONDS)
        with lock:
            if not state["running"]:
                return
            if STAGES[state["stage_idx"]] == "CUT" and state["force_spike_queued"]:
                state["force_spike_queued"] = False
                state["force_spike_active"] = True
            state["stage_idx"] += 1
            if state["stage_idx"] >= len(STAGES):
                run_inspection()
                state["running"] = False
                state["status"] = "READY"
                state["stage_idx"] = len(STAGES)
                return
            update_sensors()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state")
def api_state():
    with lock:
        if state["running"]:
            update_sensors()
        return jsonify({
            "running": state["running"],
            "stage_idx": state["stage_idx"],
            "stages": STAGES,
            "status": state["status"],
            "force_spike_active": state["force_spike_active"],
            "sensors": state["sensors"],
            "params": state["params"],
            "adaptive": state.get("adaptive"),
            "last_inspection": state.get("last_inspection"),
        })


@app.route("/api/control/start", methods=["POST"])
def api_start():
    global worker_thread
    with lock:
        if state["running"]:
            return jsonify({"ok": False, "message": "already running"}), 409
        state["running"] = True
        state["force_spike_active"] = False
        state["last_inspection"] = None
        state["status"] = "RUNNING"
    worker_thread = threading.Thread(target=process_worker, daemon=True)
    worker_thread.start()
    return jsonify({"ok": True})


@app.route("/api/control/stop", methods=["POST"])
def api_stop():
    with lock:
        state["running"] = False
        state["status"] = "STOPPED"
    return jsonify({"ok": True})


@app.route("/api/control/reset", methods=["POST"])
def api_reset():
    with lock:
        state["running"] = False
        state["stage_idx"] = -1
        state["status"] = "READY"
        state["force_spike_active"] = False
        state["force_spike_queued"] = False
        state["last_inspection"] = None
    return jsonify({"ok": True})


@app.route("/api/control/estop", methods=["POST"])
def api_estop():
    with lock:
        state["running"] = False
        state["stage_idx"] = -1
        state["status"] = "EMERGENCY STOP"
        state["force_spike_active"] = False
        state["force_spike_queued"] = False
    return jsonify({"ok": True})


@app.route("/api/params", methods=["POST"])
def api_params():
    data = request.get_json(force=True)
    with lock:
        for key in ("feed_speed", "cut_depth", "force_limit"):
            if key in data:
                state["params"][key] = float(data[key])
    return jsonify({"ok": True, "params": state["params"]})


@app.route("/api/spike", methods=["POST"])
def api_spike():
    with lock:
        if state["running"] and state["stage_idx"] >= 0 and STAGES[state["stage_idx"]] == "CUT":
            state["force_spike_active"] = True
        else:
            state["force_spike_queued"] = True
    return jsonify({"ok": True})


@app.route("/api/specimens")
def api_specimens():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT specimen_id, diameter, cut_depth, max_force, length, result, created_at "
        "FROM specimens ORDER BY id DESC LIMIT 100"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/export")
def api_export():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT specimen_id, diameter, cut_depth, max_force, length, result, created_at "
        "FROM specimens ORDER BY id DESC"
    ).fetchall()
    conn.close()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["ID", "Diameter(mm)", "CutDepth(mm)", "MaxForce(N)", "Length(mm)", "Result", "Time"])
    for r in rows:
        writer.writerow([r["specimen_id"], r["diameter"], r["cut_depth"], r["max_force"],
                          r["length"], r["result"], r["created_at"]])
    mem = io.BytesIO(buf.getvalue().encode("utf-8"))
    mem.seek(0)
    return send_file(mem, mimetype="text/csv", as_attachment=True,
                      download_name="inzora_specimen_log.csv")


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)

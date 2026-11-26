import os
import sqlite3
from datetime import datetime
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

# En Render, /tmp persiste mientras el contenedor esta activo;
# si necesitas persistencia permanente entre reinicios/deploys, conecta un Disk o BD externa.
DB_PATH = os.environ.get("DB_PATH", "/tmp/nivel_agua.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mediciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dispositivo TEXT NOT NULL DEFAULT 'esp32-agua',
                distancia_cm REAL NOT NULL,
                nivel_cm REAL NOT NULL,
                porcentaje REAL NOT NULL,
                estado TEXT NOT NULL,
                altura_cm REAL NOT NULL,
                creado_en TEXT NOT NULL
            )
            """
        )
        conn.commit()


def calcular_estado(porcentaje):
    if porcentaje < 30.0:
        return "Bajo"
    if porcentaje <= 70.0:
        return "Medio"
    return "Alto"


def normalizar_lectura(payload):
    if not isinstance(payload, dict):
        raise ValueError("El cuerpo debe ser un objeto JSON.")

    if "distancia_cm" not in payload:
        raise ValueError("Falta el campo 'distancia_cm'.")

    distancia_cm = float(payload["distancia_cm"])
    if distancia_cm < 0:
        raise ValueError("'distancia_cm' no puede ser negativa.")

    altura_raw = payload.get("altura_cm", payload.get("altura_recipiente_cm", 16.0))
    altura_cm = float(altura_raw)
    if altura_cm <= 0:
        raise ValueError("'altura_cm' debe ser mayor que 0.")

    # Si el ESP32 ya manda nivel_cm y porcentaje validos, los usamos; si no, los calculamos
    if "nivel_cm" in payload and payload["nivel_cm"] is not None:
        nivel_cm = max(0.0, min(altura_cm, float(payload["nivel_cm"])))
    else:
        nivel_cm = max(0.0, min(altura_cm, altura_cm - distancia_cm))

    if "porcentaje" in payload and payload["porcentaje"] is not None:
        porcentaje = max(0.0, min(100.0, float(payload["porcentaje"])))
    else:
        porcentaje = (nivel_cm / altura_cm) * 100.0

    estado_enviado = payload.get("estado")
    if isinstance(estado_enviado, str) and estado_enviado.strip() in ("Bajo", "Medio", "Alto"):
        estado = estado_enviado.strip()
    else:
        estado = calcular_estado(porcentaje)

    dispositivo = str(payload.get("dispositivo") or "esp32-agua").strip()[:60]
    creado_en = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    return {
        "dispositivo": dispositivo,
        "distancia_cm": round(distancia_cm, 2),
        "nivel_cm": round(nivel_cm, 2),
        "porcentaje": round(porcentaje, 1),
        "estado": estado,
        "altura_cm": round(altura_cm, 2),
        "creado_en": creado_en,
    }


init_db()


HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Monitor de Nivel de Agua — ESP32</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root {
      --bg: #0b1220;
      --card: #131c31;
      --border: #24324d;
      --text: #f1f5f9;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --bajo: #ef4444;
      --medio: #f59e0b;
      --alto: #22c55e;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      padding: 20px;
    }
    .container { max-width: 1000px; margin: 0 auto; }
    header {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      margin-bottom: 20px;
    }
    h1 { margin: 0; font-size: 1.5rem; color: var(--accent); }
    .sub { color: var(--muted); font-size: 0.9rem; }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 14px;
      margin-bottom: 20px;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px;
    }
    .label { color: var(--muted); font-size: 0.85rem; margin-bottom: 6px; }
    .value { font-size: 1.8rem; font-weight: 700; }
    .badge {
      display: inline-block;
      padding: 4px 10px;
      border-radius: 999px;
      font-weight: 700;
      font-size: 0.9rem;
      color: #090d16;
    }
    .estado-Bajo { background: var(--bajo); color: #fff; }
    .estado-Medio { background: var(--medio); }
    .estado-Alto { background: var(--alto); }
    .panel {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 20px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.9rem;
    }
    th, td {
      text-align: left;
      padding: 10px 8px;
      border-bottom: 1px solid var(--border);
    }
    th { color: var(--muted); font-weight: 600; }
    .table-wrap { overflow-x: auto; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>Monitor de Nivel de Agua</h1>
        <div class="sub" id="ultima-actualizacion">Esperando lecturas del ESP32...</div>
      </div>
      <div class="sub">Endpoint: <code>/api/recibir_nivel</code></div>
    </header>

    <section class="grid">
      <div class="card">
        <div class="label">Porcentaje de llenado</div>
        <div class="value" id="val-porcentaje">--%</div>
      </div>
      <div class="card">
        <div class="label">Nivel de agua</div>
        <div class="value" id="val-nivel">-- cm</div>
      </div>
      <div class="card">
        <div class="label">Distancia medida (HC-SR04)</div>
        <div class="value" id="val-distancia">-- cm</div>
      </div>
      <div class="card">
        <div class="label">Estado del recipiente</div>
        <div class="value"><span class="badge" id="val-estado">Sin datos</span></div>
      </div>
    </section>

    <section class="panel">
      <div class="label">Variación histórica del nivel (%)</div>
      <canvas id="graficaNivel" height="95"></canvas>
    </section>

    <section class="panel">
      <div class="label">Historial reciente</div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Fecha / Hora</th>
              <th>Dispositivo</th>
              <th>Distancia</th>
              <th>Nivel</th>
              <th>Porcentaje</th>
              <th>Estado</th>
            </tr>
          </thead>
          <tbody id="tabla-historial">
            <tr><td colspan="6" class="sub">Cargando mediciones...</td></tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>

  <script>
    const ctx = document.getElementById("graficaNivel").getContext("2d");
    const chart = new Chart(ctx, {
      type: "line",
      data: {
        labels: [],
        datasets: [{
          label: "Porcentaje (%)",
          data: [],
          borderColor: "#38bdf8",
          backgroundColor: "rgba(56, 189, 248, 0.15)",
          tension: 0.25,
          fill: true
        }]
      },
      options: {
        responsive: true,
        scales: {
          y: { min: 0, max: 100, ticks: { color: "#94a3b8" }, grid: { color: "#24324d" } },
          x: { ticks: { color: "#94a3b8", maxTicksLimit: 8 }, grid: { color: "#24324d" } }
        },
        plugins: { legend: { labels: { color: "#f1f5f9" } } }
      }
    });

    function aplicarEstadoBadge(el, estado) {
      el.className = "badge";
      if (estado === "Bajo" || estado === "Medio" || estado === "Alto") {
        el.classList.add("estado-" + estado);
      }
      el.textContent = estado || "Sin datos";
    }

    async function refrescarDatos() {
      try {
        const res = await fetch("/api/historial?limite=40");
        if (!res.ok) return;
        const data = await res.json();
        const items = data.mediciones || [];

        if (items.length > 0) {
          const actual = items[0];
          document.getElementById("val-porcentaje").textContent = actual.porcentaje + "%";
          document.getElementById("val-nivel").textContent = actual.nivel_cm + " cm";
          document.getElementById("val-distancia").textContent = actual.distancia_cm + " cm";
          aplicarEstadoBadge(document.getElementById("val-estado"), actual.estado);
          document.getElementById("ultima-actualizacion").textContent =
            "Última lectura (" + actual.dispositivo + "): " + actual.creado_en;
        }

        const cronologico = [...items].reverse();
        chart.data.labels = cronologico.map(x => x.creado_en.replace(" UTC", ""));
        chart.data.datasets[0].data = cronologico.map(x => x.porcentaje);
        chart.update();

        const tbody = document.getElementById("tabla-historial");
        if (items.length === 0) {
          tbody.innerHTML = '<tr><td colspan="6" class="sub">Aún no hay mediciones registradas.</td></tr>';
          return;
        }

        tbody.innerHTML = items.slice(0, 20).map(row => `
          <tr>
            <td>${row.creado_en}</td>
            <td>${row.dispositivo}</td>
            <td>${row.distancia_cm} cm</td>
            <td>${row.nivel_cm} cm</td>
            <td>${row.porcentaje}%</td>
            <td><span class="badge estado-${row.estado}">${row.estado}</span></td>
          </tr>
        `).join("");
      } catch (err) {
        console.error("Error actualizando dashboard:", err);
      }
    }

    refrescarDatos();
    setInterval(refrescarDatos, 5000);
  </script>
</body>
</html>
"""


@app.get("/")
def index():
    return render_template_string(HTML_DASHBOARD)


@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.post("/api/recibir_nivel")
def recibir_nivel():
    payload = request.get_json(silent=True)
    if payload is None and request.form:
        payload = request.form.to_dict()

    try:
        lectura = normalizar_lectura(payload)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    with get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO mediciones (
                dispositivo, distancia_cm, nivel_cm, porcentaje, estado, altura_cm, creado_en
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lectura["dispositivo"],
                lectura["distancia_cm"],
                lectura["nivel_cm"],
                lectura["porcentaje"],
                lectura["estado"],
                lectura["altura_cm"],
                lectura["creado_en"],
            ),
        )
        conn.commit()
        lectura["id"] = cur.lastrowid

    return jsonify({"ok": True, "medicion": lectura}), 201


@app.get("/api/ultima")
def ultima_medicion():
    with get_db() as conn:
        row = conn.execute("SELECT * FROM mediciones ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        return jsonify({"ok": True, "medicion": None}), 200
    return jsonify({"ok": True, "medicion": dict(row)}), 200


@app.get("/api/historial")
def historial():
    try:
        limite = max(1, min(500, int(request.args.get("limite", 50))))
    except ValueError:
        limite = 50

    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM mediciones ORDER BY id DESC LIMIT ?",
            (limite,),
        ).fetchall()

    return jsonify({"ok": True, "mediciones": [dict(r) for r in rows]}), 200


if __name__ == "__main__":
    puerto = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=puerto)

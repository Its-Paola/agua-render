from datetime import datetime
import os
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

lecturas = []
MAX_LECTURAS = 100

HTML_PANEL = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Nivel de Agua - Render</title>
  <style>
    body { font-family: Arial, sans-serif; max-width: 720px; margin: 30px auto; padding: 0 16px; }
    table { width: 100%; border-collapse: collapse; margin-top: 16px; }
    th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
    th { background: #f4f4f4; }
  </style>
</head>
<body>
  <h2>Monitor de Nivel de Agua (Render)</h2>
  {% if ultima %}
    <p><b>Ultimo nivel:</b> {{ ultima.nivel_cm }} cm ({{ ultima.porcentaje }}%) — <b>Estado:</b> {{ ultima.estado }}</p>
    <p><b>Distancia al sensor:</b> {{ ultima.distancia_cm }} cm | <b>Hora:</b> {{ ultima.hora }}</p>
  {% else %}
    <p>Aun no hay lecturas recibidas desde el ESP32.</p>
  {% endif %}

  <table>
    <thead>
      <tr>
        <th>Hora</th>
        <th>Nivel (cm)</th>
        <th>Porcentaje</th>
        <th>Distancia (cm)</th>
        <th>Estado</th>
      </tr>
    </thead>
    <tbody>
      {% for item in historial %}
      <tr>
        <td>{{ item.hora }}</td>
        <td>{{ item.nivel_cm }}</td>
        <td>{{ item.porcentaje }}%</td>
        <td>{{ item.distancia_cm }}</td>
        <td>{{ item.estado }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</body>
</html>
"""


@app.route("/")
def inicio():
    ultima = lecturas[-1] if lecturas else None
    return render_template_string(
        HTML_PANEL, ultima=ultima, historial=list(reversed(lecturas[-25:]))
    )


@app.route("/api/recibir_nivel", methods=["POST"])
def recibir_nivel():
    data = request.get_json(silent=True) or {}
    try:
        registro = {
            "hora": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "distancia_cm": float(data["distancia_cm"]),
            "nivel_cm": float(data["nivel_cm"]),
            "porcentaje": float(data["porcentaje"]),
            "estado": str(data.get("estado", "Desconocido")),
        }
    except (KeyError, TypeError, ValueError):
        return jsonify({"ok": False, "error": "JSON invalido o faltan campos"}), 400

    lecturas.append(registro)
    if len(lecturas) > MAX_LECTURAS:
        del lecturas[0 : len(lecturas) - MAX_LECTURAS]

    return jsonify({"ok": True, "recibido": registro}), 200


@app.route("/api/historial", methods=["GET"])
def historial():
    return jsonify({"total": len(lecturas), "datos": lecturas}), 200


if __name__ == "__main__":
    puerto = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=puerto)
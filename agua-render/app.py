from datetime import datetime
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# Guarda los últimos 100 cambios/lecturas en memoria (para algo permanente usa SQLite o Postgres en Render)
historial = []
ultima_lectura = None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/lectura", methods=["POST"])
def recibir_lectura():
    global ultima_lectura
    datos = request.get_json(silent=True) or {}

    requeridos = ("distancia_cm", "nivel_cm", "porcentaje", "estado")
    if not all(k in datos for k in requeridos):
        return jsonify({"ok": False, "error": "Faltan campos"}), 400

    registro = {
        "distancia_cm": float(datos["distancia_cm"]),
        "nivel_cm": float(datos["nivel_cm"]),
        "porcentaje": float(datos["porcentaje"]),
        "estado": str(datos["estado"]),
        "hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    ultima_lectura = registro
    historial.append(registro)
    if len(historial) > 100:
        historial.pop(0)

    return jsonify({"ok": True, "recibido": registro}), 200


@app.route("/api/datos")
def obtener_datos():
    return jsonify({"actual": ultima_lectura, "historial": historial})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

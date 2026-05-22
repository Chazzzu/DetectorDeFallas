"""
app.py
Servidor Flask del Sistema de Inspección Modular ITT.
Headless: la única interfaz es web, accesible desde la red local.
"""

from flask import Flask, render_template, jsonify, Response, send_from_directory, send_file, request
from datetime import datetime
import os
import socket

from database import InspectionDB
from inspector import InspectorService


# --- Inicialización ---
app = Flask(__name__)

# Configuración via variables de entorno (con defaults razonables)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("INSPECTOR_DATA_DIR", BASE_DIR)
MODELOS_DIR = os.environ.get("INSPECTOR_MODELOS_DIR", os.path.join(BASE_DIR, "modelos"))
# Fuente de video: acepta índice numérico ("0"), URL RTSP/HTTP, o ruta de archivo
CAMARA_SOURCE = os.environ.get("INSPECTOR_CAMERA_SOURCE",
                                os.environ.get("INSPECTOR_CAMERA_IDX", "0"))
PORT = int(os.environ.get("INSPECTOR_PORT", "5000"))

# Asegurar que el directorio de datos exista
os.makedirs(DATA_DIR, exist_ok=True)

CAPTURAS_DIR = os.path.join(DATA_DIR, "capturas_defectos")
DB_PATH = os.path.join(DATA_DIR, "inspecciones.db")

db = InspectionDB(db_path=DB_PATH)
inspector = InspectorService(
    db=db,
    carpeta_capturas=CAPTURAS_DIR,
    carpeta_modelos=MODELOS_DIR,
    camara_source=CAMARA_SOURCE
)


# --- Rutas Web (HTML) ---
@app.route("/")
def index():
    return render_template("index.html")


# --- API REST ---
@app.route("/api/stats")
def api_stats():
    """Estadísticas en vivo (calculadas en memoria)."""
    return jsonify(inspector.obtener_stats_vivo())


@app.route("/api/historial")
def api_historial():
    """Últimas N detecciones desde la DB."""
    limit = request.args.get("limit", default=50, type=int)
    historial = db.obtener_historial(limit=limit)
    return jsonify(historial)


@app.route("/api/modelo/<nombre>", methods=["POST"])
def api_cargar_modelo(nombre):
    """Cargar un modelo: pcb, frutas, general."""
    mapeo = {
        "pcb":     ("modelo_pcb.pt",    "PCB - Defectos Electrónicos"),
        "frutas":  ("modelo_frutas.pt", "FRUTAS - Podredumbre"),
        "general": ("yolo11n.pt",       "GENERAL - Librería Abierta")
    }
    if nombre not in mapeo:
        return jsonify({"ok": False, "msg": "Modelo no válido"}), 400

    archivo, etiqueta = mapeo[nombre]
    ok, msg = inspector.cargar_modelo(archivo, etiqueta)
    return jsonify({"ok": ok, "msg": msg})


@app.route("/api/limpiar", methods=["POST"])
def api_limpiar():
    """Limpia la base de datos (NO borra las imágenes en disco)."""
    db.limpiar_todo()
    inspector.contador_clases.clear()
    inspector.suma_confianzas = 0.0
    inspector.total_detecciones = 0
    return jsonify({"ok": True, "msg": "Historial limpiado"})


# --- Gestión de cámara/fuente de video ---
@app.route("/api/camara/cambiar", methods=["POST"])
def api_cambiar_camara():
    """Cambia la fuente de video en caliente."""
    data = request.get_json(silent=True) or {}
    nueva_fuente = data.get("fuente", "").strip()
    if not nueva_fuente:
        return jsonify({"ok": False, "msg": "Fuente vacía"}), 400
    ok, msg = inspector.cambiar_fuente(nueva_fuente)
    return jsonify({"ok": ok, "msg": msg})


@app.route("/api/camara/refrescar", methods=["POST"])
def api_refrescar_camara():
    """Reintenta la conexión con la fuente actual."""
    ok, msg = inspector.refrescar_camara()
    return jsonify({"ok": ok, "msg": msg})


# --- Streaming de video ---
@app.route("/video_feed")
def video_feed():
    return Response(
        inspector.generar_stream(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


# --- Servir imágenes capturadas ---
@app.route("/capturas/<path:filename>")
def servir_captura(filename):
    return send_from_directory(CAPTURAS_DIR, filename)


# --- Datos agregados para el gráfico (top N clases) ---
@app.route("/api/grafico")
def api_grafico():
    """Devuelve la distribución de detecciones por clase para graficar."""
    stats = db.obtener_estadisticas()
    # Limita a top 10 clases para que el gráfico sea legible
    por_clase = stats.get("por_clase", [])[:10]
    return jsonify({
        "labels": [item["clase"] for item in por_clase],
        "valores": [item["c"] for item in por_clase],
        "total": stats.get("total", 0)
    })


# --- Descarga de la base de datos completa ---
@app.route("/api/descargar/db")
def api_descargar_db():
    """Envía el archivo de SQLite con un nombre amigable."""
    if not os.path.exists(DB_PATH):
        return jsonify({"ok": False, "msg": "Base de datos no encontrada"}), 404
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return send_file(
        DB_PATH,
        as_attachment=True,
        download_name=f"inspecciones_{timestamp}.db",
        mimetype="application/x-sqlite3"
    )


# --- Descarga del historial en CSV (extra útil) ---
@app.route("/api/descargar/csv")
def api_descargar_csv():
    """Exporta el historial completo a CSV para Excel/análisis."""
    import csv, io
    historial = db.obtener_historial(limit=100000)  # todo
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Timestamp", "Hora", "Modelo", "Clase", "Confianza", "Descripción", "Imagen"])
    for h in historial:
        writer.writerow([h["id"], h["timestamp"], h["hora"], h["modelo"],
                         h["clase"], h["confianza"], h.get("descripcion", ""), h["ruta_imagen"]])

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=inspecciones_{timestamp}.csv"}
    )


# --- Helper: obtener IP local para mostrar en logs ---
def obtener_ip_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# --- Arranque ---
if __name__ == "__main__":
    inspector.start()  # arranca el thread de captura+inferencia
    ip = obtener_ip_local()
    print("\n" + "="*60)
    print("  SISTEMA DE INSPECCIÓN MODULAR - ITT (modo web)")
    print("="*60)
    print(f"  Local:   http://localhost:{PORT}")
    print(f"  Red:     http://{ip}:{PORT}")
    print("="*60 + "\n")
    try:
        # host=0.0.0.0 → accesible desde otros equipos de la red
        # threaded=True → permite múltiples clientes simultáneos
        app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
    finally:
        inspector.stop()

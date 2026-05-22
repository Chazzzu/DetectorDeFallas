"""
database.py
Manejo de SQLite para el sistema de inspección.
Patrón: metadata en DB + imágenes en filesystem.
"""

import sqlite3
import threading
from datetime import datetime
from contextlib import contextmanager


class InspectionDB:
    def __init__(self, db_path="inspecciones.db"):
        self.db_path = db_path
        # Lock para escritura segura desde múltiples threads
        self._lock = threading.Lock()
        self._init_schema()

    @contextmanager
    def _get_conn(self):
        """Conexión por operación. SQLite así es seguro en multi-thread."""
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row  # Para acceder columnas por nombre
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self):
        """Crea la tabla si no existe."""
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS detecciones (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   TEXT    NOT NULL,
                    fecha       TEXT    NOT NULL,
                    hora        TEXT    NOT NULL,
                    modelo      TEXT    NOT NULL,
                    clase       TEXT    NOT NULL,
                    confianza   REAL    NOT NULL,
                    descripcion TEXT,
                    ruta_imagen TEXT    NOT NULL
                )
            """)
            # Índice para acelerar consultas por fecha
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON detecciones(timestamp DESC)")

    def insertar_deteccion(self, modelo, clase, confianza, ruta_imagen, descripcion=""):
        """Inserta un evento de detección. Thread-safe."""
        with self._lock:
            ahora = datetime.now()
            with self._get_conn() as conn:
                cursor = conn.execute("""
                    INSERT INTO detecciones (timestamp, fecha, hora, modelo, clase, confianza, descripcion, ruta_imagen)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ahora.isoformat(),
                    ahora.strftime("%Y-%m-%d"),
                    ahora.strftime("%H:%M:%S"),
                    modelo,
                    clase,
                    round(confianza, 4),
                    descripcion,
                    ruta_imagen
                ))
                return cursor.lastrowid

    def obtener_historial(self, limit=50):
        """Devuelve las últimas N detecciones."""
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT id, timestamp, hora, modelo, clase, confianza, descripcion, ruta_imagen
                FROM detecciones
                ORDER BY id DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def obtener_estadisticas(self):
        """Devuelve estadísticas agregadas."""
        with self._get_conn() as conn:
            total = conn.execute("SELECT COUNT(*) as c FROM detecciones").fetchone()["c"]

            if total == 0:
                return {"total": 0, "confianza_promedio": 0.0, "clase_top": None, "veces_top": 0, "por_clase": []}

            conf_avg = conn.execute("SELECT AVG(confianza) as avg FROM detecciones").fetchone()["avg"]

            top = conn.execute("""
                SELECT clase, COUNT(*) as c
                FROM detecciones
                GROUP BY clase
                ORDER BY c DESC
                LIMIT 1
            """).fetchone()

            por_clase = conn.execute("""
                SELECT clase, COUNT(*) as c
                FROM detecciones
                GROUP BY clase
                ORDER BY c DESC
                LIMIT 10
            """).fetchall()

            return {
                "total": total,
                "confianza_promedio": round(conf_avg, 4),
                "clase_top": top["clase"] if top else None,
                "veces_top": top["c"] if top else 0,
                "por_clase": [dict(r) for r in por_clase]
            }

    def limpiar_todo(self):
        """Borra todos los registros (mantiene la tabla)."""
        with self._lock:
            with self._get_conn() as conn:
                conn.execute("DELETE FROM detecciones")

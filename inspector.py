"""
inspector.py
Servicio de inspección que corre en un thread separado.
Captura frames, ejecuta YOLO, guarda en DB y genera frames para streaming.
"""

import cv2
import os
import threading
import time
from datetime import datetime
from collections import Counter
from ultralytics import YOLO
import torch

from database import InspectionDB


class InspectorService:
    def __init__(self, db: InspectionDB, carpeta_capturas="capturas_defectos",
                 carpeta_modelos="modelos", camara_source=0):
        self.db = db
        self.carpeta_capturas = carpeta_capturas
        self.carpeta_modelos = carpeta_modelos
        self.camara_source = camara_source

        os.makedirs(self.carpeta_capturas, exist_ok=True)
        os.makedirs(self.carpeta_modelos, exist_ok=True)

        # --- Estado del modelo ---
        self.model = None
        self.model_name = "Sin Modelo"

        # --- Detección de dispositivo ---
        if torch.cuda.is_available():
            self.device = 0
            self.device_name = torch.cuda.get_device_name(0)
            print(f"✅ GPU detectada: {self.device_name}")
        else:
            self.device = "cpu"
            self.device_name = "CPU"
            print("⚠️  Usando CPU")

        # --- Apertura de fuente de video (webcam, RTSP, HTTP, archivo) ---
        self.vid = self._abrir_fuente_video(camara_source)
        self.fuente_disponible = self.vid is not None and self.vid.isOpened()

        if self.fuente_disponible:
            print(f"✅ Fuente de video lista: {camara_source}")
        else:
            print(f"⚠️  No se pudo abrir la fuente '{camara_source}' - se mostrará pantalla 'Sin señal'")

        # --- Estado interno ---
        self.frame_actual = None  # último frame anotado para streaming
        self.frame_lock = threading.Lock()
        self.tiempo_inicio = datetime.now()
        self.contador_clases = Counter()
        self.suma_confianzas = 0.0
        self.total_detecciones = 0
        self._ultimo_log = datetime.now()
        self._intervalo_log = 3.0  # segundos entre capturas (anti-spam)

        self._running = False
        self._thread = None

        # Cargar contador inicial desde la DB (en caso de reinicio)
        stats = self.db.obtener_estadisticas()
        self.total_detecciones = stats["total"]
        if stats["total"] > 0:
            self.suma_confianzas = stats["confianza_promedio"] * stats["total"]
            for entry in stats["por_clase"]:
                self.contador_clases[entry["clase"]] = entry["c"]

    # --- Apertura de fuente de video (acepta webcam, RTSP, HTTP, archivo) ---
    def _abrir_fuente_video(self, source):
        """
        Abre cualquier tipo de fuente de video.
        Acepta:
          - int (0, 1, 2...) → webcam local
          - string numérico ("0", "1") → webcam local
          - URL RTSP ("rtsp://...") → cámara IP
          - URL HTTP ("http://...") → MJPEG stream o cámara IP
          - Ruta de archivo ("/data/video.mp4") → archivo de video
        Devuelve un VideoCapture abierto, o None si falla.
        """
        # Convertir string numérico a int (webcam)
        if isinstance(source, str):
            try:
                source = int(source)
            except ValueError:
                pass  # Mantener como string (URL o ruta)

        tipo = "webcam" if isinstance(source, int) else "stream/archivo"
        print(f"Abriendo fuente de video ({tipo}): {source}")

        cap = cv2.VideoCapture(source)
        if cap.isOpened():
            return cap

        # Si era webcam y falló, probar otros índices
        if isinstance(source, int):
            print(f"⚠️  Índice {source} no abrió, probando otros...")
            for idx in [0, 1, 2]:
                if idx == source:
                    continue
                cap = cv2.VideoCapture(idx)
                if cap.isOpened():
                    print(f"✅ Webcam abierta en índice {idx}")
                    return cap
            return None

        # Si era URL/archivo, no hay alternativas
        return None

    def _generar_frame_sin_senal(self):
        """Genera un frame placeholder cuando no hay cámara disponible."""
        import numpy as np
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[:] = (44, 62, 80)  # Color #2c3e50 (mismo del tema)
        cv2.putText(frame, "SIN SENAL DE VIDEO", (130, 220),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        cv2.putText(frame, f"Fuente: {self.camara_source}", (140, 270),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        cv2.putText(frame, "Revise INSPECTOR_CAMERA_SOURCE", (90, 320),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (150, 150, 150), 1)
        return frame

    # --- Cambio/refresco de fuente en caliente ---
    def cambiar_fuente(self, nueva_fuente):
        """Cambia la fuente de video sin reiniciar la app."""
        print(f"🔄 Cambiando fuente: {self.camara_source} → {nueva_fuente}")

        # Liberar la cámara actual (con lock para no chocar con el loop)
        with self.frame_lock:
            if self.vid is not None:
                self.vid.release()
            self.vid = None
            self.fuente_disponible = False

        self.camara_source = nueva_fuente

        # Intentar abrir la nueva fuente
        nueva_vid = self._abrir_fuente_video(nueva_fuente)
        if nueva_vid is not None and nueva_vid.isOpened():
            with self.frame_lock:
                self.vid = nueva_vid
                self.fuente_disponible = True
            return True, f"Fuente conectada: {nueva_fuente}"
        else:
            return False, f"No se pudo abrir la fuente: {nueva_fuente}"

    def refrescar_camara(self):
        """Reintenta la conexión con la fuente actual (útil si se cayó)."""
        return self.cambiar_fuente(self.camara_source)

    # --- Carga de modelos ---
    def cargar_modelo(self, nombre_archivo, etiqueta):
        ruta = os.path.join(self.carpeta_modelos, nombre_archivo)
        if not os.path.exists(ruta):
            # Permite que YOLO descargue yolo11n.pt si no existe
            if nombre_archivo == "yolo11n.pt":
                ruta = "yolo11n.pt"
            else:
                return False, f"No se encontró: {ruta}"
        try:
            self.model = YOLO(ruta)
            self.model_name = etiqueta
            print(f"Modelo cargado: {etiqueta} en {self.device_name}")
            return True, f"Modelo {etiqueta} cargado"
        except Exception as e:
            return False, f"Error cargando modelo: {e}"

    # --- Loop principal de inferencia (corre en thread) ---
    def _loop(self):
        while self._running:
            # Si no hay fuente disponible, mostrar pantalla de "Sin señal"
            if not self.fuente_disponible:
                with self.frame_lock:
                    self.frame_actual = self._generar_frame_sin_senal()
                time.sleep(0.5)  # No hace falta refrescar tan rápido
                continue

            ret, frame = self.vid.read()
            if not ret:
                # Si es archivo de video, reiniciar al final
                if isinstance(self.camara_source, str) and not self.camara_source.startswith(("http", "rtsp")):
                    self.vid.set(cv2.CAP_PROP_POS_FRAMES, 0)
                time.sleep(0.05)
                continue

            if self.model is not None:
                try:
                    results = self.model.predict(source=frame, conf=0.45,
                                                 device=self.device, verbose=False)
                    frame_anotado = results[0].plot()

                    # Registrar primera detección si pasaron N segundos
                    if len(results[0].boxes) > 0:
                        ahora = datetime.now()
                        if (ahora - self._ultimo_log).total_seconds() >= self._intervalo_log:
                            box = results[0].boxes[0]
                            clase_id = int(box.cls[0])
                            nombre_clase = self.model.names[clase_id]
                            conf = float(box.conf[0])
                            self._guardar_deteccion(nombre_clase, conf, frame_anotado)
                            self._ultimo_log = ahora

                    frame_para_stream = frame_anotado
                except Exception as e:
                    print(f"Error en inferencia: {e}")
                    frame_para_stream = frame
            else:
                # Sin modelo, dibujamos texto de aviso sobre el frame
                cv2.putText(frame, "Sin modelo cargado", (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                frame_para_stream = frame

            # Guardar frame actual para streaming MJPEG
            with self.frame_lock:
                self.frame_actual = frame_para_stream

    def _guardar_deteccion(self, clase, confianza, frame_anotado):
        """Guarda la imagen JPG y registra en la base de datos."""
        ahora = datetime.now()
        timestamp = ahora.strftime("%Y%m%d_%H%M%S")
        nombre_archivo = f"{timestamp}_{clase}_{confianza:.2f}.jpg"
        ruta_imagen = os.path.join(self.carpeta_capturas, nombre_archivo)

        cv2.imwrite(ruta_imagen, frame_anotado)

        descripcion = f"Detección automática de '{clase}' por modelo {self.model_name}"
        self.db.insertar_deteccion(
            modelo=self.model_name,
            clase=clase,
            confianza=confianza,
            ruta_imagen=nombre_archivo,
            descripcion=descripcion
        )

        # Actualizar estadísticas en memoria
        self.contador_clases[clase] += 1
        self.suma_confianzas += confianza
        self.total_detecciones += 1
        print(f"📸 LOG: {clase} ({confianza:.2f}) -> {nombre_archivo}")

    # --- Control del thread ---
    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("🟢 Inspector iniciado")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if self.vid:
            self.vid.release()
        print("🔴 Inspector detenido")

    # --- Generador para streaming MJPEG ---
    def generar_stream(self):
        """Yield de frames JPEG para Flask Response."""
        while True:
            with self.frame_lock:
                frame = self.frame_actual
            if frame is None:
                time.sleep(0.05)
                continue
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if not ok:
                continue
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n")
            time.sleep(0.05)  # ~20 fps máximo en stream

    # --- Estadísticas en vivo (memoria) ---
    def obtener_stats_vivo(self):
        ahora = datetime.now()
        delta = ahora - self.tiempo_inicio
        segs_totales = int(delta.total_seconds())
        horas = segs_totales // 3600
        minutos = (segs_totales % 3600) // 60
        segs = segs_totales % 60

        ritmo = 0.0
        if segs_totales > 0 and self.total_detecciones > 0:
            ritmo = (self.total_detecciones / segs_totales) * 60

        confianza_avg = 0.0
        if self.total_detecciones > 0:
            confianza_avg = (self.suma_confianzas / self.total_detecciones) * 100

        clase_top = None
        veces_top = 0
        if self.contador_clases:
            clase_top, veces_top = self.contador_clases.most_common(1)[0]

        return {
            "tiempo_sesion": f"{horas:02d}:{minutos:02d}:{segs:02d}",
            "total": self.total_detecciones,
            "ritmo_por_min": round(ritmo, 1),
            "confianza_promedio": round(confianza_avg, 1),
            "clase_top": clase_top,
            "veces_top": veces_top,
            "modelo_activo": self.model_name,
            "dispositivo": self.device_name,
            "camara_fuente": str(self.camara_source),
            "camara_activa": self.fuente_disponible
        }

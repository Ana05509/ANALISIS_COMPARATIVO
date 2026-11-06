"""
Configuración de Gunicorn para producción (Railway). Sin variables de entorno
se comporta igual que el Procfile anterior: 1 worker síncrono, timeout 180 s.

Variables (ver docs/09_rama_mejoras_seguridad_estabilidad.md):
  WEB_CONCURRENCY          procesos (workers). Cada uno ocupa ~160 MB en reposo
                           y ~300 MB al generar un Excel con gráficos (Kaleido
                           abre Chromium). Calcular con la RAM real del plan.
  GUNICORN_THREADS         hilos por worker. Dejar en 1: los reportes usan
                           matplotlib.pyplot (estado global, no apto para hilos).
  GUNICORN_TIMEOUT         segundos antes de reiniciar un worker colgado.
  GUNICORN_MAX_REQUESTS    reciclar el worker tras N peticiones (0 = nunca), para
                           acotar el crecimiento de memoria de pandas/matplotlib.
"""
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", "1"))
threads = int(os.environ.get("GUNICORN_THREADS", "1"))
worker_class = "gthread" if threads > 1 else "sync"
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "180"))
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", "0"))
max_requests_jitter = max_requests // 10
accesslog = "-"
errorlog = "-"

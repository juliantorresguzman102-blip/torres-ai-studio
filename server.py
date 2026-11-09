"""Torres AI Studio - servidor MVP: foto, texto, narración offline opcional, MP4.
No genera sincronización de labios ni animación facial de IA.
Archivos procesados en un directorio temporal y eliminados después de cada pedido.
"""
import base64
import binascii
import io
import json
import logging
import math
import os
import shutil
import subprocess
import tempfile
import textwrap
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

PORT = int(os.environ.get("PORT", "10000"))
MAX_REQUEST = 24 * 1024 * 1024
MAX_IMAGE = 8 * 1024 * 1024
MAX_AUDIO = 10 * 1024 * 1024
MAX_SCRIPT = 420
MAX_DURATION = 35
RENDERER = threading.BoundedSemaphore(1)
ORIGINS = {
    "https://juliantorresguzman102-blip.github.io",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:8001",
    "http://127.0.0.1:8001",
}
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
Image.MAX_IMAGE_PIXELS = 25_000_000


def parse_data_uri(value, limit, label):
    if not isinstance(value, str) or not value.startswith("data:") or "," not in value:
        raise ValueError(f"{label}: enviá un archivo válido.")
    header, encoded = value.split(",", 1)
    if ";base64" not in header or len(encoded) > (limit * 4 // 3 + 20):
        raise ValueError(f"{label}: archivo inválido o demasiado grande.")
    try:
        blob = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as e:
        raise ValueError(f"{label}: no se pudo leer el archivo.") from e
    if not blob or len(blob) > limit:
        raise ValueError(f"{label}: archivo vacío o demasiado grande.")
    return blob


def run_tool(args, *, input_text=None, timeout=120):
    try:
        result = subprocess.run(args, input=input_text, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("La generación tardó demasiado. Probá con un video más corto.") from exc
    if result.returncode != 0:
        logging.warning("Media command failed: %s", result.stderr[-1500:])
        raise ValueError("No se pudo procesar el audio o el video. Probá con otro archivo.")
    return result


def audio_duration(path):
    result = run_tool([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path)
    ], timeout=15)
    try:
        seconds = float(result.stdout.strip())
    except ValueError as exc:
        raise ValueError("No se pudo leer la duración del audio.") from exc
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("El archivo de audio no tiene una duración válida.")
    return seconds


def caption_segments(text, horizontal):
    # Leyendas aproximadas a lo largo del video, NO subtítulos sincronizados palabra a palabra.
    line_width = 42 if horizontal else 25
    words = text.split()
    segments, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > line_width * 2 and current:
            segments.append(current)
            current = word
        else:
            current = candidate
    if current:
        segments.append(current)
    return ["\n".join(textwrap.wrap(s, width=line_width)) for s in segments]


def make_video(data):
    if not isinstance(data, dict):
        raise ValueError("Solicitud inválida.")
    raw_image = parse_data_uri(data.get("image"), MAX_IMAGE, "Imagen")
    try:
        with Image.open(io.BytesIO(raw_image)) as image:
            image = ImageOps.exif_transpose(image)
            if image.width * image.height > 24_000_000:
                raise ValueError("La foto es demasiado grande. Usá una foto más pequeña.")
            if image.mode != "RGB":
                rgba = image.convert("RGBA")
                background = Image.new("RGBA", rgba.size, (14, 21, 38, 255))
                background.alpha_composite(rgba)
                image = background.convert("RGB")
            else:
                image = image.copy()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("La imagen no es válida. Probá con JPG, PNG o WebP.") from exc

    voice = data.get("voice_mode", "tts")
    if voice not in ("tts", "upload", "none"):
        raise ValueError("Modo de voz inválido.")
    script = " ".join(str(data.get("script") or "").strip().split())
    if len(script) > MAX_SCRIPT:
        raise ValueError(f"El guion tiene demasiados caracteres. Máximo {MAX_SCRIPT}.")
    if voice == "tts" and not script:
        raise ValueError("Escribí un guion para crear la narración.")
    if voice == "upload" and not data.get("audio"):
        raise ValueError("Seleccioná un archivo de voz o elegí narración automática.")
    if data.get("format") not in ("vertical", "horizontal"):
        raise ValueError("Formato de video inválido.")
    horizontal = data["format"] == "horizontal"
    width, height = (854, 480) if horizontal else (480, 854)
    try:
        selected_duration = int(data.get("duration", 8))
    except (TypeError, ValueError) as exc:
        raise ValueError("Duración inválida.") from exc
    duration = max(3, min(MAX_DURATION, selected_duration))

    with tempfile.TemporaryDirectory(prefix="torres-ai-") as temp:
        tempdir = Path(temp)
        image.thumbnail((2200, 2200))
        photo = tempdir / "photo.jpg"
        image.save(photo, quality=89)
        sound = None
        if voice == "upload":
            sound = tempdir / "uploaded_audio"
            sound.write_bytes(parse_data_uri(data["audio"], MAX_AUDIO, "Audio"))
        elif voice == "tts":
            synthesizer = shutil.which("espeak-ng") or shutil.which("espeak")
            if synthesizer is None:
                raise RuntimeError("El motor de voz aún no está instalado en el servidor.")
            sound = tempdir / "narracion.wav"
            # Motor sin cuotas externas. La voz es robótica, NO clonación ni TTS neuronal.
            run_tool([synthesizer, "-v", "es-la", "-s", "150", "-w", str(sound), "--stdin"],
                     input_text=script, timeout=30)
        if sound is not None:
            duration = min(MAX_DURATION, max(2, audio_duration(sound) + 0.15))

        output = tempdir / "video.mp4"
        vf = (f"scale={width}:{height}:force_original_aspect_ratio=increase,"
              f"crop={width}:{height},"
              f"zoompan=z='min(zoom+0.00018,1.055)':d=1:s={width}x{height}:fps=20,"
              "format=yuv420p")
        if script:
            captions = caption_segments(script, horizontal)
            per_segment = duration / len(captions)
            for i, line in enumerate(captions):
                path = tempdir / f"caption{i}.txt"
                path.write_text(line, encoding="utf-8")
                start, end = i * per_segment, (i + 1) * per_segment
                vf += (f",drawtext=textfile='{path}':"
                       f"fontcolor=white:fontsize={23 if not horizontal else 22}:"
                       "borderw=3:bordercolor=black:line_spacing=6:"
                       f"x=(w-text_w)/2:y=h-text_h-{56 if not horizontal else 34}:"
                       f"enable='between(t,{start:.2f},{end:.2f})'")

        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                   "-threads", "1", "-loop", "1", "-framerate", "20", "-i", str(photo)]
        if sound:
            command += ["-i", str(sound)]
        command += ["-t", f"{duration:.2f}", "-vf", vf, "-map", "0:v:0",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                    "-pix_fmt", "yuv420p", "-r", "20", "-movflags", "+faststart"]
        if sound:
            command += ["-map", "1:a:0", "-c:a", "aac", "-b:a", "96k", "-shortest"]
        else:
            command += ["-an"]
        command.append(str(output))
        run_tool(command, timeout=160)
        if not output.exists() or output.stat().st_size < 200:
            raise RuntimeError("No se produjo un video válido.")
        return output.read_bytes()


class Handler(BaseHTTPRequestHandler):
    server_version = "TorresAIStudio/1.2"

    def respond(self, status, data, content_type="application/json"):
        origin = self.headers.get("Origin", "")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if origin in ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        if data:
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                logging.info("Cliente desconectado antes de recibir el video")

    def json(self, status, value):
        self.respond(status, json.dumps(value, ensure_ascii=False).encode("utf-8"))

    def do_OPTIONS(self):
        if self.path == "/generate":
            self.respond(204, b"")
        else:
            self.json(404, {"error": "Ruta no encontrada."})

    def do_GET(self):
        if self.path in ("/", "/health"):
            self.json(200, {"status": "ok", "app": "Torres AI Studio", "version": "1.2", "tts": bool(shutil.which("espeak-ng") or shutil.which("espeak"))})
        else:
            self.json(404, {"error": "Ruta no encontrada."})

    def do_POST(self):
        if self.path != "/generate":
            self.json(404, {"error": "Ruta no encontrada."})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > MAX_REQUEST:
                self.json(413, {"error": "La solicitud supera el límite de 24 MB."})
                return
        except ValueError:
            self.json(400, {"error": "Tamaño de solicitud inválido."})
            return
        if not RENDERER.acquire(blocking=False):
            self.json(503, {"error": "El servidor está procesando otro video. Esperá un momento."})
            return
        try:
            data = json.loads(self.rfile.read(size))
            output = make_video(data)
            self.respond(200, output, "video/mp4")
        except (ValueError, json.JSONDecodeError) as exc:
            self.json(400, {"error": str(exc)})
        except Exception:
            logging.exception("Video generation error")
            self.json(500, {"error": "No se pudo generar el video. Probá con otra imagen o un video más corto."})
        finally:
            RENDERER.release()


if __name__ == "__main__":
    logging.info("Torres AI Studio iniciado en el puerto %s", PORT)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

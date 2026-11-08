import base64, json, os, subprocess, tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT=int(os.environ.get("PORT","8000")) 
MAX_BYTES=32*1024*1024

class Handler(BaseHTTPRequestHandler):
    def send_headers(self,code,kind="application/json",size=None):
        self.send_response(code)
        self.send_header("Content-Type",kind)
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","POST, OPTIONS, GET")
        self.send_header("Access-Control-Allow-Headers","Content-Type")
        if size is not None:self.send_header("Content-Length",str(size))
        self.end_headers()
    def do_OPTIONS(self):self.send_headers(204)
    def do_GET(self):
        body=b'{"status":"ok"}'
        self.send_headers(200,size=len(body));self.wfile.write(body)
    def do_POST(self):
        if self.path!="/generate":
            self.send_headers(404)
        try:
            n=int(self.headers.get("Content-Length","0"))
            if not 0<n<MAX_BYTES:raise ValueError("Archivo demasiado grande")
            data=json.loads(self.rfile.read(n))
            def decode(value):
                return base64.b64decode(value.split(",",1)[1],validate=True)
            with tempfile.TemporaryDirectory() as tmp:
                d=Path(tmp);(d/"image").write_bytes(decode(data["image"]))
                audio=data.get("audio")
                if audio:(d/"audio").write_bytes(decode(audio))
                vertical=data.get("format")!="horizontal"
                w,h=(720,1280) if vertical else (1280,720)
                duration=max(1,min(120,int(data.get("duration",8))))
                vf=f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},zoompan=z='min(zoom+0.0003,1.08)':d=1:s={w}x{h}:fps=25,format=yuv420p"
                cmd=["ffmpeg","-hide_banner","-loglevel","error","-y","-loop","1","-framerate","25","-i",str(d/"image")]
                if audio:
                    cmd+=["-i",str(d/"audio")]
                else:cmd+=["-t",str(duration)]
                script=str(data.get("script","")).strip()
                if script:
                    # Texto simple, escapado mediante archivo para evitar inyección en filtros.
                    (d/"caption.txt").write_text(script[:500],encoding="utf-8")
                    vf+=f",drawtext=textfile={d/'caption.txt'}:fontcolor=white:fontsize=34:borderw=3:bordercolor=black:x=(w-text_w)/2:y=h-130"
                cmd+=["-vf",vf]
                if audio:cmd+=["-map","0:v:0","-map","1:a:0","-shortest","-c:a","aac","-b:a","128k"]
                cmd+=["-c:v","libx264","-preset","veryfast","-crf","26","-pix_fmt","yuv420p","-movflags","+faststart",str(d/"video.mp4")]
                run=subprocess.run(cmd,capture_output=True,text=True,timeout=240)
                if run.returncode:raise RuntimeError(run.stderr[-500:])
                result=(d/"video.mp4").read_bytes()
            self.send_headers(200,"video/mp4",len(result))
        except Exception as e:
            body=json.dumps({"error":str(e)},ensure_ascii=False).encode()
            self.send_headers(400,size=len(body))
if __name__=="__main__":
    ThreadingHTTPServer(("0.0.0.0",PORT),Handler).serve_forever()

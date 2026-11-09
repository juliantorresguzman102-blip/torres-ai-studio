# Torres AI Studio — MVP 1.2

Actualización de la plataforma publicada en GitHub Pages con backend en Render.

## Qué funciona
- Generación de MP4 a partir de fotografía y guion.
- Voz sintética automática en español mediante espeak-ng offline, sin créditos por video (voz básica/robótica).
- Alternativamente, MP3/M4A/WAV subidos por el usuario.
- Texto dividido en tarjetas temporizadas aproximadamente; **no es subtitulado preciso**.
- Video en formato vertical u horizontal, vista previa y descarga, optimizado para móvil.
- CORS limitado al dominio GitHub Pages, duración y tamaños máximos, un render a la vez.

## Qué NO está incluido
- Movimiento labial, avatar facial realista ni voz neuronal clonada tipo HeyGen.
- Cuentas de usuario, almacenamiento permanente, cola de procesamiento ni escalado.
- Videos ilimitados garantizados: el servidor Render gratuito tiene límites operativos.

## Publicación

Subí **server.py, Dockerfile, index.html, sw.js y manifest.webmanifest** al directorio raíz del repositorio
https://github.com/juliantorresguzman102-blip/torres-ai-studio
(reemplazando archivos de los mismos nombres; no borres icon.png ni manifest.webmanifest).

- Render tiene autodeploy desde la rama `main` y volverá a construir el backend.
- GitHub Pages publicará automáticamente el nuevo `index.html`.
- Esperá hasta que Render muestre `Live` y comprobá `https://torres-ai-studio.onrender.com/health`.
- Abrí `https://juliantorresguzman102-blip.github.io/torres-ai-studio/` para probar.

## Desarrollo local

```
pip install 'Pillow>=10,<14'
# En Linux: instalar ffmpeg y espeak-ng
python server.py
```

El puerto predeterminado es 10000, configurable con variable PORT.
No subas fotografías sensibles a un servidor público sin revisar los términos de privacidad y seguridad.

# Vendor

Dependencias de terceros empaquetadas para que el visor funcione **offline**
(sin CDN, coherente con `AGENTS.md`).

| Archivo | Origen | Versión | Licencia |
| --- | --- | --- | --- |
| `three.min.js` | `three@0.149.0/build/three.min.js` (jsDelivr) | r149 | MIT (`three.LICENSE`) |
| `three.LICENSE` | `three@0.149.0/LICENSE` | r149 | MIT |

## ¿Por qué r149 y no la última?

`three.min.js` es un build **UMD** que se carga con `<script>` clásico. Es lo
único que funciona sin fricción cuando la página se abre con `file://`
(`QWebEngineView.load(QUrl.fromLocalFile(...))`): los **ES modules** se bloquean
por CORS con origen `null`, que es justo el bug detectado en este proyecto.

three.js **eliminó los builds UMD en r150**. Alternativas cuando llegue la
feature `viewer-3d`:

1. Servir el visor con un esquema Qt propio (`QWebEngineUrlSchemeHandler`, p. ej.
   `rig://viewer/`) y usar `three.module.js` + import map.
2. Empaquetar los recursos en `qrc:` y cargar con `qrc:/viewer/index.html`.

Ambas permiten módulos ES sin depender de `file://`, y son el camino previsto
para WebGL con cámara real, iluminación PBR y skinning en GPU.

## Actualizar

```powershell
Invoke-WebRequest -Uri https://cdn.jsdelivr.net/npm/three@0.149.0/build/three.min.js -OutFile viewer\vendor\three.min.js
```

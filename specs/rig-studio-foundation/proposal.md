# Propuesta de cambio: `rig-studio-foundation`

| Campo | Valor |
| --- | --- |
| **Feature** | `rig-studio-foundation` |
| **Agente** | `sdd-propose` |
| **Fecha** | 2026-11-16 |
| **Fases cubiertas** | Fase 0 (bootstrap) · Fase 1 (contrato de escena) · Fase 2 (canal + malla + núcleo geométrico) |
| **Estado** | Propuesta — insumo para `spec.md` y `design.md` |
| **Predecesoras** | Ninguna (scaffolding ya creado) |

---

## 1. Intención

El proyecto tiene las cuatro capas creadas, pero **ninguna frontera está verificada de extremo a extremo**:
la app arranca sin poder cargar nada, `py_bridge` no tiene modelo de datos, el visor dibuja un placeholder
y el núcleo Rust nunca se ha compilado en esta máquina (no hay `rustup`/`cargo`/`maturin`).

Esta feature convierte el scaffolding en un **esqueleto caminante (*walking skeleton*)**: un único camino
real, fino y ejecutable que atraviesa las cuatro capas —**malla de ejemplo → `Scene` en Python → JSON → visor
con malla renderizada → AABB/normales calculados en Rust**— más el *tooling* que hace ese camino reproducible
(`cargo`, `maturin`, `pytest`, `ruff`, CI).

**Por qué ahora:** los tres riesgos estructurales del proyecto (extensión nativa que no se compila ni se
importa, contrato de escena inexistente y ausencia de canal app→visor) son baratos de cerrar *antes* de
escribir lógica de rigging. Si se posponen, cada feature posterior heredaría el mismo punto de fallo y
el coste de reparación crece con el código encima. Además, el contrato de escena es el insumo de **todas**
las features posteriores: fijarlo mal obliga a reescribir importación, skinning y exportación.

---

## 2. Alcance

### Incluido

**Fase 0 — Bootstrap reproducible**
- Toolchain Rust completa (`rustup` stable ≥ 1.88, MSVC, `maturin`).
- `core_rust` compila y `import core_rust` devuelve el módulo real; se elimina la dependencia de
  renombrar `.dll → .pyd` a mano.
- `pyproject.toml` raíz (ruff + pytest config), `ruff`, `pytest`, `pytest-qt` en `requirements-dev.txt`.
- Workflow de CI (Windows + Linux): `cargo fmt --check`, `clippy -D warnings`, `cargo test --no-default-features`,
  `maturin develop`, `pytest`, `ruff check`.
- Script de arranque único (`scripts/bootstrap.ps1` o equivalente) que deja el entorno listo.

**Fase 1 — Contrato de escena y modelo de datos**
- `py_bridge/scene.py`: dataclasses inmutables `Mesh` (vértices `(V,3)` float32, caras `(F,3)` int32,
  normales opcionales), `Skeleton` (joints `(J,3)`, `parents: tuple[int, ...]` con `-1` en raíces,
  `names: tuple[str, ...]`), `Scene` (`mesh`, `skeleton | None`, `name`, `metadata`).
- Serialización versionada: `Scene.to_dict()` / `to_json()` con `schema_version` explícito y
  `specs/scene-contract/scene.schema.json` (JSON Schema) como fuente de verdad.
- Validación de invariantes en `__post_init__` (formas, `parents[i] < i` o `-1`, índices de caras en rango,
  huesos derivados de `parents`) con errores accionables en español.
- Fixtures: malla de ejemplo empaquetada (`assets/meshes/`) generada o importada como cubo/grid.
- `py_bridge/__init__.py` expone la API pública nueva (`Mesh`, `Skeleton`, `Scene`, `load_mesh_file` stub).

**Fase 2 — Canal, visor y núcleo geométrico**
- **Canal app→viewer:** `app/viewer_bridge.py` con un `QObject` publicado por `QWebChannel` (`bridge.sceneChanged(json)`)
  y `qwebchannel.js` *vendored* en `viewer/`; fallback documentado a `page().runJavaScript(...)` si el
  `QWebChannel` no engancha. El visor ignora `schema_version` desconocido sin lanzar excepción.
- **Visor:** render de malla con relleno de caras + *painter's algorithm* / z-sorting, *wireframe* opcional,
  selección por clic (resaltado local), y contadores reales (`V vértices · F caras`). Mantiene la API
  `window.RigViewer.setScene(...)` y degrada si la escena falta.
- **Núcleo Rust** (`core_rust`): `bounds`, `normals` (por área, acumuladas y normalizadas), `normalize_vertices`,
  `mesh_stats` (V, F, AABB, longitud de aristas total) leyendo **`PyBuffer<f32>` / `PyBuffer<u32>` zero-copy**
  (sin `Vec<f32>` intermedio en el camino caliente) con `py.detach` en todo lo que supere ~5 ms.
- **Benches** con `criterion` y un test de contrato que verifique el camino zero-copy y el rechazo de
  arrays no conformes.
- Hilo de trabajo mínimo: una operación larga (carga/estadísticas) ejecutada fuera del hilo de UI con
  señales Qt y estado en la barra de estado.

### Excluido (explícitamente)

- **MagicArticulate real**: no se descargan pesos ni se ejecuta inferencia. Solo se define su frontera
  (protocolo + `NotImplementedError` accionable) y se elige la arquitectura *sidecar*.
- **Skinning LBS** y matrices de pose (feature `core-skinning`).
- **Exportación** glTF/GLB y empaquetado/distribución (PyInstaller, wheels del producto).
- **Importación de formatos**: solo la malla de ejemplo empaquetada (la lectura de OBJ/STL/PLY va a `mesh-import`).
- Render 3D real (WebGL/three.js), cámara con perspectiva, iluminación y materiales.
- Skinning en GPU, simulación física, animación y retargeting.

---

## 3. Enfoque sugerido

### Alternativa A — *Walking skeleton* por fases verticales (recomendada)

Construir un corte delgado pero completo en tres fases consecutivas, cada una con su propio criterio de
verificación: (0) el entorno compila y arranca, (1) el contrato de escena existe y valida, (2) la escena
viaja de Python al visor y el núcleo la mide.

- **Ventajas:** ataca primero los puntos de fallo integradores (extensión nativa, JSON, `QWebChannel`),
  que son los que hoy no están probados en absoluto. Cada fase deja algo demostrable, lo que permite
  corregir el contrato de escena con el visor ya consumiéndolo. Las features posteriores (`mesh-import`,
  `core-skinning`, `export-rig`) se enchufan al contrato sin renegociarlo.
- **Desventajas:** el núcleo geométrico arranca con alcance mínimo (AABB, normales, normalización) y
  no con operaciones de rigging; hay trabajo "de fontanería" (CI, `pyproject.toml`) que no se ve en la UI.

### Alternativa B — Núcleo primero (*core-first*)

Invertir el orden: llevar `core_rust` a un estado maduro (geometría completa, decimación, jerarquías,
benches) y solo después construir `Scene`, el canal y el render.

- **Ventajas:** el activo más valioso (el núcleo nativo) se estabiliza pronto; los tests Rust son de
  ciclo rápido y no dependen de Qt ni de Python.
- **Desventajas:** el contrato de escena se diseña en el vacío y el primer contacto con el visor llega
  tarde, cuando ya hay mucha API Rust comprometida. El "¿la app funciona?" sigue sin respuesta durante
  toda la feature, y un fallo de integración (p. ej. `abi3` + buffer protocol) obligaría a rehacer firmas.

**Recomendación: Alternativa A.** El riesgo dominante hoy no es algorítmico sino de integración
(`.pyd` que no carga, contrato que cambia, `QWebChannel` que no engancha en `file://`), y la Alternativa A
lo expone en la primera semana. La Alternativa B es válida como estrategia *después* del MVP, cuando el
contrato ya esté congelado.

### Decisión clave 1 — MagicArticulate: *in-process* vs *sidecar*

| Criterio | In-process (torch en el venv de la app) | **Sidecar (venv propio + IPC)** |
| --- | --- | --- |
| Versión de Python | La app queda atada a la que soporte torch/`pytorch3d` | App libre (3.15); sidecar fijado a 3.12/3.13 |
| `pytorch3d` / ops CUDA en Windows | Compilación desde fuente, requiere CUDA Toolkit + MSVC compatible; wheels precompilados casi inexistentes para cp315 | Aislado: se resuelve (o se deja en CPU) sin condicionar el resto |
| Arranque de la app | Import de torch al primer uso, cientos de MB residentes | App ligera; el proceso pesado se lanza bajo demanda |
| Fallo del modelo | Puede tumbar el proceso de UI | Degrada: la UI reporta el error del sidecar y sigue viva |
| Latencia | Sin IPC (mejor en mallas pequeñas) | IPC + serialización (coste acotado: enviar `(V,3)+(F,3)` una vez) |
| Empaquetado futuro | Muy difícil (torch + CUDA dentro del instalador) | Natural: el sidecar se distribuye aparte o se descarga |

**Recomendación: sidecar**, con el contrato IPC definido ya en esta feature (JSON + binario/base64 o
archivo temporal `.npz` referenciado por ruta) y **un *spike* acotado** (≤ 1 día) que valide si
MagicArticulate corre en CPU con el torch estándar: si el spike demuestra que **no** necesita
`pytorch3d` ni kernels CUDA y funciona en el Python de la app, se permite degradar a *in-process* sin
cambiar la interfaz (`MagicArticulateBackend`), porque la frontera ya está aislada. La decisión inversa
(empezar *in-process* y migrar a sidecar después) no es viable sin reescribir el arranque y el empaquetado.

**Implicación para esta feature:** `MagicArticulateBackend` mantiene su API actual y documenta que la
implementación vivirá detrás de un *transporte*; `load()`/`articulate()` siguen lanzando
`NotImplementedError` con mensaje que apunta a la feature `magicarticulate-backend`.

### Decisión clave 2 — Protocolo de escena JSON versionado

Formato plano, sin dependencias y estable:

```json
{
  "schema_version": 1,
  "name": "cubo",
  "mesh": {
    "vertices": [0.0, 0.0, 0.0],
    "faces": [0, 1, 2],
    "normals": null,
    "vertex_count": 8,
    "face_count": 12
  },
  "skeleton": {
    "joints": [[0.0, 0.0, 0.0]],
    "parents": [-1],
    "names": ["root"],
    "bones": [[0, 0]]
  },
  "metadata": { "source": "example://cube", "units": "m" }
}
```

Reglas del contrato:
- `schema_version` es **entero mayor**; el visor acepta `1` y muestra un aviso no fatal para versiones
  mayores desconocidas. Cambios incompatibles suben el mayor; campos nuevos opcionales no lo suben.
- Los brazos `mesh`/`skeleton` son `null`-ables; una escena sin esqueleto es válida (caso Fase 2).
- `parents[i] ∈ {-1} ∪ [0, i)` → árbol garantizado, sin ciclos; `bones` es derivado, nunca fuente de verdad.
- Las listas numéricas son planas y *row-major* (el visor reconstruye índices), lo que evita ambigüedad
  de anidamiento y mantiene el parser trivial en JS.
- `scene.schema.json` se versiona en `specs/scene-contract/` y un test de `pytest` valida *fixtures*
  contra él: el esquema no es documentación, es un test.
- Sin `numpy` en `app/`: la conversión y la serialización viven en `py_bridge/scene.py`.

---

## 4. Riesgos iniciales

| # | Riesgo | Impacto | Mitigación |
| --- | --- | --- | --- |
| R1 | **No hay toolchain Rust** en la máquina (`cargo`/`rustc`/`maturin` ausentes) | Alto: nada del núcleo se verifica | Fase 0 instala `rustup` stable (≥1.88) + `maturin` como primer entregable; el resto de la feature no empieza hasta que `cargo build --release` pase |
| R2 | **Python 3.15 muy nuevo**: PyO3 0.30.1 puede rechazar cp315 al compilar | Alto: bloquea el import | Compilar con `abi3-py311`; si el *build script* falla, `PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1` y, en último caso, venv de compilación en 3.13 documentado en `README` |
| R3 | **MSVC 2026 + Rust**: `link.exe`/`vswhere` no detectado por versiones antiguas del `cc`/`link` | Medio | Usar el `stable` más reciente; validar con un `cargo build` de humo antes de tocar `lib.rs` |
| R4 | **Buffer protocol bajo `abi3`**: el zero-copy puede no ser viable con la API limitada | Alto: obligaría a copiar en el camino caliente | Prototipo temprano con `PyBuffer<f32>`/`PyBuffer<u32>` (API estable ≥3.11); *fallback* aceptado: `Vec<f32>` con coste medido y umbral documentado |
| R5 | **`QWebChannel` no carga en `file://`** o falta `qwebchannel.js` | Medio | Vendorizar `qwebchannel.js` en `viewer/`; *fallback* a `page().runJavaScript` para el canal descendente; probar en Fase 0 con un "ping" |
| R6 | **Deriva del contrato** entre Python y JS (campos que se renombran) | Medio | `schema_version` + JSON Schema + test de *fixtures*; el visor valida al entrar |
| R7 | **Scope creep** hacia MagicArticulate/skinning/exportación | Medio | Sección "Excluido" vinculante; cualquier añadido requiere nueva propuesta |
| R8 | **`pytorch3d`/CUDA en Windows** si se elige *in-process* | Alto (futuro) | Decisión de sidecar ya tomada; *spike* acotado con puerta explícita |
| R9 | **Bloqueo del hilo de UI** al medir mallas grandes | Medio | `py.detach` en Rust + operación en `QThreadPool` con señales; criterio de éxito con malla de 1M vértices |
| R10 | **CI ruidosa** por diferencias Windows/Linux (rutas, `.pyd/.so`) | Bajo | Dos jobs con `matrix.os`; rutas vía `pathlib`; `_native/` en `.gitignore` |

---

## 5. Roadmap de features posteriores

Orden de ejecución sugerido. "Absorbida" = su alcance entra en `rig-studio-foundation`; queda cerrada al
terminar esta feature.

| # | Feature | Objetivo | Depende de | Estado |
| --- | --- | --- | --- | --- |
| 1 | **`qa-ci`** | `pyproject.toml` raíz, ruff, pytest, CI Windows/Linux, script de bootstrap | — | **Absorbida (Fase 0)** |
| 2 | **`scene-contract`** | `Mesh`/`Skeleton`/`Scene` + `scene.schema.json` v1 + validación | `qa-ci` | **Absorbida (Fase 1)** |
| 3 | **`viewer-bridge`** | Canal app→viewer (`QWebChannel` + JSON versionado), degradación segura | `scene-contract` | **Absorbida (Fase 2)** |
| 4 | **`core-geometry`** | `bounds`/`normals`/`normalize`/`mesh_stats` con buffer protocol, `py.detach`, benches | `scene-contract` | **Absorbida parcial (Fase 2)**; decimación/ICP posteriores |
| 5 | **`viewer-mesh`** | Render de malla con sombreado plano, z-sorting, wireframe y selección | `viewer-bridge` | **Absorbida (Fase 2)**; picking hacia la app queda fuera |
| 6 | **`mesh-import`** | OBJ (y luego STL/PLY) → `Mesh`, deduplicación, normales suaves, errores de usuario | `scene-contract` | Posterior |
| 7 | **`app-shell`** | Paneles reales, `QThreadPool`, progreso/cancelación, diálogos de error, ajustes persistentes | `viewer-bridge` | Posterior |
| 8 | **`magicarticulate-backend`** | Sidecar con venv propio, protocolo IPC, carga de pesos, *cache*, *spike* CPU | `scene-contract`, `app-shell` | Posterior |
| 9 | **`core-skinning`** | LBS: pesos `(V,J)`, matrices de pose, jerarquía `parents`, deformación en Rust | `core-geometry` | Posterior |
| 10 | **`rig-pipeline`** | Orquestación malla → esqueleto → pesos → `Scene` lista para el visor, con estados de progreso | `magicarticulate-backend`, `core-skinning` | Posterior |
| 11 | **`export-rig`** | Exportación glTF/GLB con *skin*, joints y jerarquía | `rig-pipeline` | Posterior |
| — | **MVP demostrable (corte mínimo)** | Malla de ejemplo → auto-rig visible sobre la malla → export | #1–#11 | **Hito** |
| 12 | **`simulation`** | Física básica / colisiones sobre el esqueleto | `core-skinning` | Post-MVP |
| 13 | **`packaging`** | Instalador/distribución (PyInstaller o equivalente) + sidecar empaquetado | `export-rig`, `magicarticulate-backend` | Post-MVP |
| 14 | **`viewer-3d`** | Visor WebGL/three.js vendorizado (cámara real, iluminación, GPU skinning) | `viewer-mesh` | Post-MVP |

**Corte mínimo para un MVP demostrable:** las filas **1–11**. Si el tiempo aprieta, el único elemento
recortable es la exportación de *skin*: `export-rig` puede entregar **esqueleto sin pesos** (glTF con
nodos/jerarquía pero sin `skin`) y `core-skinning` pasa a MVP+1, manteniendo la demo
"malla de ejemplo → auto-rig visible → export".

---

## 6. Criterio de éxito medible

La feature se considera terminada cuando **todos** estos puntos se verifican en una máquina limpia:

1. **Toolchain reproducible:** `scripts/bootstrap.ps1` desde cero deja `cargo --version`, `maturin --version`
   y `.venv` funcional; `cargo build --release` produce el artefacto y `python -c "import core_rust;
   print(core_rust.version())"` imprime la versión **desde la raíz del proyecto** (sin sombra de namespace).
2. **Calidad Rust:** `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings` y
   `cargo test --no-default-features` en verde, con **≥ 8 tests** que cubran `bounds`, `normals`,
   `normalize`, `mesh_stats` y los errores de entrada inválida.
3. **Contrato validado:** `scene.schema.json` v1 existe y **≥ 3 fixtures** (solo malla, malla + esqueleto,
   escena inválida) se validan/invalidan en `pytest`; `Scene.to_dict()` es determinista (misma entrada →
   mismo JSON byte a byte).
4. **Canal operativo:** con `python -m app.main` y la malla de ejemplo, el visor muestra **la malla con
   caras sombreadas** y la barra de estado indica `V vértices · F caras` correctos; ninguna escena por
   defecto aparece como placeholder.
5. **Degradación:** cargar una escena con `schema_version: 2` deja un aviso visible y **cero excepciones**
   en la consola del visor; cargar `{}` deja el visor vacío sin errores.
6. **Núcleo geométrico:** `bounds` sobre **1M vértices** ≤ **15 ms** y `normals` sobre la misma malla
   ≤ **30 ms** en `release` (benchmark `criterion` guardado como referencia); el camino es zero-copy
   (verificado por test) y un array no conforme lanza `ValueError` con mensaje accionable, no *panic*.
7. **GIL liberado:** un test demuestra que una llamada larga al núcleo no bloquea un contador que avanza
   en el hilo principal (o, como mínimo, que `py.detach` está presente en todas las operaciones > 5 ms).
8. **QA:** `pytest` con **≥ 20 tests** en verde, `ruff check .` sin hallazgos, y el workflow de CI
   verde en `windows-latest` y `ubuntu-latest`.
9. **Arranque ligero:** `python -m app.main` abre la ventana en **< 2 s** en una máquina sin `torch`
   instalado, y la UI reporta "núcleo: no disponible" con instrucciones si la extensión falta.

---

## 7. Insumos para las siguientes fases SDD

- **Para `sdd-spec`:** los tres bloques de fase (§2) son los requisitos; los nueve criterios de §6 son
  los escenarios de aceptación. El contrato de §3.4 es normativo.
- **Para `sdd-design`:** decisiones ya cerradas que el diseño **no** debe reabrir: *walking skeleton* por
  fases, sidecar para MagicArticulate (con puerta de *spike*), JSON plano versionado con `schema_version`
  entero, `parents` como única fuente de jerarquía, y zero-copy vía `PyBuffer` con *fallback* medido.
- **Riesgo a vigilar primero:** R1 + R2 (toolchain y compatibilidad cp315) — si ambos fallan, el resto de
  la feature no es demostrable y debe replantearse el venv de compilación antes de escribir código.

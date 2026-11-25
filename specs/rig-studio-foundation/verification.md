# Verificación: `rig-studio-foundation` — Fase 1 (contrato de escena, T09–T19)

> La verificación de la **Fase 2** (núcleo geométrico) está en
> [`verification-fase-2.md`](verification-fase-2.md).

| Campo | Valor |
| --- | --- |
| **Feature** | `rig-studio-foundation` |
| **Alcance verificado** | Fase 1 — contrato de escena (T09…T19): `py_bridge/scene.py`, `py_bridge/__init__.py`, `py_bridge/magicarticulate.py`, `scene.schema.json`, `tests/`, `assets/meshes/`, `pyproject.toml` |
| **Requisitos evaluados** | RF-08, RF-09, RF-10, RF-11, RF-12 (+ RF-27 y RF-29 en la parte que toca a la fase) |
| **Escenarios** | E-08, E-13 (E-05/E-07 solo en su parte de activos de ejemplo) |
| **Criterios** | CA-09, CA-10, CA-11, CA-12 (+ CA-29 parcial) |
| **Agente** | `sdd-verify` |
| **Fecha** | 2026-11-17 |
| **Entorno** | Windows 10/11 · Python 3.15.1 · numpy 2.5.5 · pytest 9.2.0 · jsonschema 4.26.0 · ruff 0.17.5 · sin toolchain Rust |
| **Veredicto** | **PASS con observaciones** |

---

## 1. Resumen ejecutivo

El contrato de escena está implementado y es, en lo esencial, correcto: el modelo es inmutable por atributo,
`parents` es la única fuente de jerarquía, la serialización es byte a byte determinista (comprobada en tres
procesos y con ocho tamaños de troceado distintos), el esquema JSON del diseño está copiado literalmente y valida
las fixtures en ambas direcciones, y las reglas de capas se respetan sin excepciones.

Se han encontrado **dos defectos reales**, ninguno de ellos bloqueante para la Fase 2:

1. **D-1 (media):** una malla con `F = 0`, que el diseño declara válida, **no puede releerse**: el productor emite
   `"faces": []`, el esquema lo acepta, pero `Mesh.from_dict` lo rechaza porque una lista vacía se infiere como
   `float64`. Rompe `Scene.validate()` (contrato de T11) y el round-trip del documento.
2. **D-2 (baja-media):** los índices de cara que no caben en `int32` **se desbordan en silencio y se aceptan**;
   p. ej. `2**40` se convierte en `0` y pasa la validación de rango, violando RF-09 c) para documentos externos.

Las dos decisiones abiertas se consideran **correctas**: `Scene.mesh` anulable está justificado por RF-10 y por el
propio esquema, y los 16 nombres de `__all__` son exactamente el diseño §8.3 menos los cuatro que pertenecen a
T08/T29. No hay alcance de Fase 2/3 filtrado y `AGENTS.md` no se ha modificado.

---

## 2. Comandos ejecutados (resultados reales)

| Comando | Resultado |
| --- | --- |
| `.\.venv\Scripts\python.exe -m pytest -q -m "not gui"` | **89 passed in 2.08s** |
| `.\.venv\Scripts\python.exe -m pytest -q` | **89 passed in 4.70s** |
| `.\.venv\Scripts\python.exe -m pytest -q -m gui` | **89 deselected** (no existe ninguna prueba `gui` todavía) |
| `.\.venv\Scripts\python.exe -m ruff check py_bridge tests` | **All checks passed!** (ruff 0.17.5) |
| `.\.venv\Scripts\python.exe -m ruff check .` (informativo) | **1 error**: `E501 Line too long (103 > 100)` en `app\main.py:263` (código preexistente, fuera de la Fase 1) |
| `.\.venv\Scripts\python.exe -m ruff format --check py_bridge tests` (informativo) | **4 files would be reformatted, 6 files already formatted** (`py_bridge/scene.py`, `tests/conftest.py`, `tests/test_determinism.py`, `tests/test_layers.py`) |
| Script propio `verify_scene_phase1.py` | **84 comprobaciones: 79 OK · 5 fallos** → 3 fallos = 2 defectos reales (D-1 dispara dos), 1 = desviación aceptada, 1 = error del arnés propio ya corregido |

Desglose de la suite (89 pruebas):

| Archivo | Pruebas |
| --- | --- |
| `tests/test_scene.py` | 56 |
| `tests/test_scene_schema.py` | 9 |
| `tests/test_determinism.py` | 7 |
| `tests/test_layers.py` | 11 |
| `tests/test_assets.py` | 6 |

> Los números coinciden con lo declarado por `sdd-apply` en `memory.md` (89 pruebas). `ruff` sí estaba instalado
> en el venv (0.17.5), no hubo que instalarlo.

---

## 3. Tabla RF → veredicto

| Requisito | Veredicto | Evidencia |
| --- | --- | --- |
| **RF-08** Modelo `Mesh`/`Skeleton`/`Scene` con forma y dtype | **Cubierto** | `test_scene.py::test_malla_valida_normaliza_y_congela`, `::test_malla_acepta_normales`, `::test_articulaciones_comparte_memoria_y_congela`; propio: `FrozenInstanceError` al asignar, sin `__dict__` (slots), arrays internos `writeable=False`, `MappingProxyType` en `metadata` |
| **RF-09** Validación de invariantes a)–f) con error accionable | **Parcial** | 6 invariantes cubiertos: `test_scene.py::test_invariantes_de_rf09` (10 casos parametrizados a1/a2/a3/a4/b/c/d1/d2/e/f) + propio verificando que cada mensaje contiene campo + esperado + recibido y es `ValueError`; propio: `scene.py` sin ningún `assert` (AST) y validación activa con `python -O`. **Parcial por D-2**: el invariante c) no se cumple para índices fuera de `int32` |
| **RF-09 (última frase)** normalización de disposición en memoria | **Cubierto** | `test_scene.py::test_malla_comparte_memoria_si_ya_es_contigua`, `::test_malla_copia_cuando_el_dtype_no_coincide`; propio: entrada `asfortranarray` se normaliza a C-contigua sin compartir memoria |
| **RF-10** Serialización versionada y determinista | **Cubierto** | `test_determinism.py` (7 pruebas) + `test_scene.py::test_documento_canonico`, `::test_listas_planas_row_major`; propio: 3 procesos con `PYTHONHASHSEED` 0/12345/random → mismo SHA-256 `591d5875…5084f49` y mismo documento completo; 8 tamaños de `_CHUNK_ROWS` (1, 2, 3, 5, 7, 17, 65 536, 1 000 000) → bytes idénticos; `NaN` → `SceneError` (`allow_nan=False`); sin salto final; orden de claves exacto. **Matiz**: el documento determinista es correcto, pero una malla con `F = 0` no se puede releer (D-1, sección 6) |
| **RF-11** Jerarquía con fuente única (`parents`) | **Cubierto** | `test_scene.py::test_bones_ignorados_en_entrada` (`bones` mentiroso `[[4,4],[0,3]]` → se ignora y se recalcula), `::test_bones_derivados`, `::test_bones_se_recalculan_al_cambiar_parents`, `::test_bones_no_es_parametro_del_constructor`; propio: 5 casos `parents[i] ≥ i` rechazados, `parents[i] < -1` rechazado, 4 ciclos propuestos rechazados, recorrido hoja→raíz acotado |
| **RF-12** Esquema JSON como prueba automatizada | **Cubierto** | `test_scene_schema.py` (9 pruebas): 2 fixtures válidas + `scene_v2` validan, `scene_invalid_face_index` falla **en esquema y en `Scene.from_dict`** (doble vía, D-14), `to_dict()`/`to_json()` del productor validan (con esqueleto, solo malla, `mesh: null`, solo esqueleto). Propio: el archivo es **estructuralmente idéntico** al literal de `design.md` §3.6 (extraído por script y comparado) y `Draft202012Validator.check_schema` pasa |
| **RF-27** Calidad Python (parcial, lo que toca a la fase) | **Parcial** | 89 pruebas ≥ 20 en verde ✔; `ruff check py_bridge tests` limpio ✔; `ruff check .` deja 1 hallazgo preexistente en `app/main.py:263` ✘ (ver O-5). El resto de RF-27 (UI, núcleo nativo) pertenece a T07/T43 |
| **RF-29** Frontera del modelo ML (parcial) | **Parcial** | `test_layers.py::test_torch_solo_se_importa_dentro_de_funciones`, `::test_mensaje_de_feature_pendiente_nombra_la_feature`; propio: `import py_bridge` y `import app.main` con `"torch" not in sys.modules`; `PendingFeatureError(NotImplementedError)` con mensaje que nombra `magicarticulate-backend`. La parte de UI (panel de estado, < 2 s) es T43 |

---

## 4. Tabla CA → veredicto

| CA | Veredicto | Evidencia |
| --- | --- | --- |
| **CA-09** Esquema v1 + ≥ 3 casos validados automáticamente | **Cubierto** | `test_scene_schema.py::test_el_esquema_es_de_draft_2020_12`, `::test_fixture_valida_pasa_el_esquema` (×2), `::test_fixture_invalida_falla_en_esquema_y_en_python`, `::test_el_productor_cumple_el_contrato`; 5 fixtures en `tests/fixtures/` (2 válidas, 1 inválida, `scene_v2`, `{}`) |
| **CA-10** JSON idéntico byte a byte en dos procesos | **Cubierto** | `test_determinism.py::test_dos_procesos_producen_el_mismo_documento`, `::test_el_hash_coincide_con_la_serializacion_local`, `::test_troceado_produce_los_mismos_bytes`, `::test_la_escena_grande_coincide_con_su_troceado`; propio con 3 procesos y 8 tamaños de bloque (SHA-256 idéntico) |
| **CA-11** Seis invariantes rechazados, cada uno con ≥ 1 prueba | **Cubierto** | `test_scene.py::test_invariantes_de_rf09` (10 IDs: a1, a2, a3, a4, b, c, d1, d2, e, f) + propio con las 10 plantillas exactas (campo/esperado/recibido). Reserva: D-2 afecta a c) solo con enteros > `int32` |
| **CA-12** Escena sin esqueleto válida; huesos derivados de `parents` | **Cubierto** | `test_scene.py::test_escena_sin_esqueleto`, `::test_bones_derivados`, `::test_bones_ignorados_en_entrada`; `test_assets.py::test_escena_rigged_de_ejemplo` (bones `((1,0),(2,1),(3,2),(4,2))`) |
| **CA-29** ≥ 20 pruebas pytest verdes + análisis estático sin hallazgos | **Parcial** | 89 passed ✔; `ruff check py_bridge tests` limpio ✔; `ruff check .` con 1 E501 en `app/main.py` ✘ (preexistente, ver O-5) |

---

## 5. Escenarios

| Escenario | Veredicto | Evidencia |
| --- | --- | --- |
| **E-08 — Escena inválida** | **Parcial** | A nivel de contrato: índice fuera de rango, `parents[i] ≥ i` y dtype distinto se rechazan con mensaje en español que nombra campo, esperado y recibido (`test_scene.py::test_invariantes_de_rf09`, `::test_fixture_con_indice_invalido_es_rechazada`). La parte de UI (barra de estado, "el visor permanece en su estado anterior") es Fase 3. Con D-2, un documento con índice `≥ 2**32` no se rechaza |
| **E-13 — Determinismo y validación por esquema** | **Cubierto** | `test_determinism.py` + `test_scene_schema.py` + `test_assets.py`; propio: mismo SHA-256 en 3 procesos, fixtures válidas aceptadas, inválida rechazada, derivación de huesos esperada |
| **E-05 / E-07 — Carga del activo y selección** | **Cubierto (solo el insumo)** | `test_assets.py`: `example_cube.scene.json` (8 V / 12 F, sin esqueleto) y `example_rigged.scene.json` (8 V / 12 F / 5 J / 4 huesos) cargan con `load_scene_file`. El render y el picking son Fase 3 (T35–T42) |

---

## 6. Comprobaciones propias (no delegadas a los tests del implementador)

Script `verify_scene_phase1.py` (84 comprobaciones, fuera del repositorio). Agrupadas:

**`parents` como única fuente (RF-11/RF-09 e)**
- `bones` con contenido falso en el JSON → se ignora; `bones` emitido = derivado de `parents`. ✔
- `bones` no es parámetro del constructor (`TypeError`). ✔
- Cambiar `parents` cambia `bones` (propiedad calculada, nunca almacenada). ✔
- `parents[i] ≥ i` rechazado en 5 posiciones distintas; `parents[i] < i` aceptado. ✔
- `parents[i] = -2` rechazado. ✔
- Cuatro ciclos propuestos (`(-1,0,2,1)`, `(0,1)`, `(-1,1,0)`, `(-1,0,1,2,4)`) rechazados: el ciclo es estructuralmente imposible porque cada padre es estrictamente menor que su hijo. ✔
- Recorrido hoja→raíz del esqueleto de ejemplo termina en la raíz sin superar `J` pasos. ✔

**Determinismo (RF-10/CA-10)**
- SHA-256 de la escena canónica en 3 subprocesos (`PYTHONHASHSEED` = 0, 12345, random): `591d58757977229daa0ee5bdec2aceb0dbd6a1c7a4de4b985fa483d1a5084f49`, idéntico. ✔
- Documento completo comparado (no solo el hash), con nombre no ASCII `ñandú` y metadatos anidados. ✔
- Ocho tamaños de `_CHUNK_ROWS` (1…1 000 000) → bytes idénticos. ✔
- Fracciones de progreso monótonas, en `[0,1]`, última `1.0`, sin duplicados. ✔
- `progress` que lanza → aborta sin devolver documento parcial. ✔
- `metadata` con distinto orden de inserción → mismo JSON. ✔
- `float32` no exactos (`0.1`, `1/3`, `-0.0`) → `repr` estable y reproducible. ✔
- `NaN` → `SceneError` (no se emite JSON inválido). ✔

**Esquema (RF-12/CA-09)**
- `Draft202012Validator.check_schema` pasa; `additionalProperties: false` en raíz y `$defs`. ✔
- `scene_mesh_only`, `scene_mesh_skeleton`, `scene_v2` válidas; `scene_invalid_face_index` inválida. ✔
- `to_dict()` valida en cuatro formas de escena (con esqueleto, solo malla, `mesh: null`, solo esqueleto). ✔
- Archivo del esquema == literal JSON de `design.md` §3.6 (extracción programática y comparación canónica). ✔

**Capas (RF-27/AGENTS.md)**
- AST sobre los 3 `.py` de `app/`: **ningún** import de `numpy`, `torch` ni `core_rust` (solo `PySide6` y `py_bridge`, que es la dirección permitida). ✔
- `numpy` solo se importa desde `py_bridge/` y `tests/`. ✔
- `torch` no aparece en imports de módulo de `magicarticulate.py` (solo dentro de funciones). ✔
- Propio: `import py_bridge` y `import app.main` (offscreen) → `torch` y `core_rust` no cargados; `core_version() == "no disponible"`. ✔

**Mensajes de error (RF-09)**
- 10 plantillas (a1…f) con campo + esperado + recibido, todas `SceneError` y `isinstance(_, ValueError)`. ✔
- 5 errores de documento (`schema_version` ausente/no entero/futuro, clave desconocida, `metadata` no serializable) con el mismo formato. ✔
- Ningún `assert` en `py_bridge/scene.py` (AST) y la validación **sigue activa con `python -O`** (subproceso). ✔
- `parents` con `float`, `bool` o `str` rechazado nombrando `Skeleton.parents`. ✔

**Activos (T19)**
- `assets/meshes/example_cube.scene.json` y `example_rigged.scene.json` son **exactamente** `Scene.to_json()` de su escena (comparación byte a byte), sin salto final, round-trip estable. ✔
- `example_rigged` → `(face_count, len(bones), joint_count) == (12, 4, 5)`, `bones == ((1,0),(2,1),(3,2),(4,2))`. ✔

**Modelo y bordes**
- `mesh_from_numpy` comparte memoria si el array ya es `float32` C-contiguo; copia si es F-contiguo o de otro dtype. ✔
- `Scene(mesh=None)` válido, emite `"mesh": null`, `validate()` funciona y el documento valida contra el esquema. ✔
- `metadata`: copia profunda, claves ascendentes, `MappingProxyType`. ✔
- **D-1:** malla con `F = 0` → **falla** el round-trip y `validate()` (ver abajo).
- **D-2:** índice `2**40` → **se acepta** con `faces=[[0,0,1]]` (ver abajo).
- Observado: `Mesh(vertices float64)` rechazado, pero `Mesh(normals float64)` aceptado y convertido (O-1).
- Observado: `Mesh(...) == Mesh(...)` con dos instancias distintas lanza `ValueError` (O-3).

**Alcance**
- No existen `py_bridge/geometry.py`, `app/viewer_bridge.py`, `app/workers.py` ni `core_rust/src/geometry.rs`. ✔
- `core_rust/**/*.rs` == `["core_rust/src/lib.rs"]`; no expone `normals`/`normalize_unit_aabb`/`mesh_stats`. ✔
- `tests/*.py` contiene solo los 6 archivos de Fase 0/1. ✔
- `AGENTS.md` con fecha 16/11 23:46, 7 641 bytes: **anterior a todos** los archivos de la Fase 1 (17/11 20:39–20:45) y con el contenido de convenciones original, sin referencias al contrato de escena. `app/main.py` y `viewer/viewer.js` conservan su fecha de 17/11 20:24 y `core_rust/src/lib.rs` la de 16/11 23:56 → **sin cambios** durante la fase. ✔

---

## 7. Defectos encontrados (con repro mínimo)

### D-1 (severidad media) — Una malla con `F = 0` no sobrevive al round-trip

`Mesh` declara válida `F = 0` (diseño §3.1, y `test_scene.py::test_malla_sin_caras_es_valida` lo confirma), el
esquema JSON también (`"faces": {..., "minItems": 0}`), pero una lista vacía se infiere como `float64` y
`_matriz_int32` la rechaza antes de convertirla.

```python
import numpy as np
from py_bridge.scene import Mesh, Scene

s = Scene(mesh=Mesh(np.zeros((3, 3), np.float32), np.zeros((0, 3), np.int32)), name="sin_caras")
s.to_json()
# {"schema_version":1,"name":"sin_caras","mesh":{"vertices":[...9 floats...],"faces":[],"normals":null,
#  "vertex_count":3,"face_count":0},"skeleton":null,"metadata":{}}
s.validate()
# py_bridge.scene.SceneError: mesh.faces: se esperaba una lista de enteros; se recibió dtype float64

Scene.from_dict(__import__("json").loads(s.to_json()))   # mismo SceneError
```

Comprobado además que ese documento **sí pasa** el esquema (`Draft202012Validator.is_valid(...) is True`).
Impacto: rompe el contrato de T11 (`validate()` ≡ `from_dict(to_dict())`), el round-trip de RF-10 para un estado
que el diseño declara válido y la futura importación de mallas sin caras (feature `mesh-import`). Lo que hace que
la suite no lo detecte es que `test_malla_sin_caras_es_valida` nunca serializa ni recarga la malla.

*Repro:* `python -c "import numpy as np; from py_bridge.scene import Mesh,Scene; Scene(mesh=Mesh(np.zeros((3,3),np.float32), np.zeros((0,3),np.int32))).validate()"`

**Arreglo sugerido** (no aplicado, es responsabilidad de `sdd-apply`): en `_plano`/`_matriz_int32`, tratar la
secuencia vacía como `np.zeros((0, 3), np.int32)` (o recibir el dtype esperado y saltarse la comprobación de
`kind` cuando `size == 0`), más una regresión que asserta
`Scene(mesh=Mesh(V, 0 caras)).validate() is None` y `from_json(to_json()).to_dict() == to_dict()`.

**Estado:** **corregido** el 2026-11-17 por `sdd-apply`. `_matriz_int32` y `_matriz_float32` devuelven
`np.zeros((0, columnas), dtype)` cuando la lista está vacía y conservan la estricta de tipo para listas no vacías.
Regresiones: `tests/test_scene.py::test_d1_malla_sin_caras_validate_es_none`,
`::test_d1_malla_sin_caras_round_trip_json`, `::test_d1_malla_sin_caras_round_trip_archivo`,
`::test_d1_normales_vacias_se_rechazan_por_forma`, `::test_d1_esqueleto_con_joints_vacio_se_rechaza_por_invariante`
y `::test_lista_de_caras_no_entera_sigue_rechazandose`.

### D-2 (severidad baja-media) — Índices de cara fuera de `int32` se desbordan y se aceptan

`_matriz_int32` convierte con `np.ascontiguousarray(..., dtype=np.int32)` (cast *unsafe*) **antes** de validar el
rango `[0, V)`, así que un entero grande se trunca y el chequeo posterior ve un índice válido.

```python
doc = {"schema_version": 1, "name": "x",
       "mesh": {"vertices": [0.0]*9, "faces": [2**40, 0, 1], "normals": None,
                "vertex_count": 3, "face_count": 1},
       "skeleton": None, "metadata": {}}
Scene.from_dict(doc).mesh.faces.tolist()   # [[0, 0, 1]]  ← aceptado
```

Medido: `2**31` → rechazado (envuelve a negativo, el chequeo lo atrapa); `2**32` → aceptado como `0`;
`2**32+5` → rechazado (envuelve a `5`, fuera de `[0,3)`); `2**40` → aceptado como `0`; `-(2**40)` → aceptado como
`0` (el esquema sí rechaza el negativo, `from_dict` no). Viola RF-09 c) («todo índice de cara debe estar en
`[0, V)`») para documentos externos. El esquema no puede cubrirlo porque no declara `maximum` y `2**40 ≥ 0`.

**Arreglo sugerido** (no aplicado): validar el rango sobre los valores en `int64` antes de castear (o rechazar
`plano.min() < INT32_MIN or plano.max() > INT32_MAX`), y añadir un caso `2**32` a la tabla de invariantes.

**Estado:** **corregido** el 2026-11-17 por `sdd-apply`. `_matriz_int32` comprueba `min`/`max` sobre el array
original **antes** de `np.ascontiguousarray(..., dtype=np.int32)` y lanza `SceneError` con
`mesh.faces: se esperaba un índice de vértice en [0, 2147483647] (int32); se recibió <valor> en la posición <i>`.
El rango `[0, V)` sigue en `Mesh.__post_init__` (design §3.2), de modo que los negativos representables en `int32`
conservan el mensaje de la plantilla c). Regresiones:
`tests/test_scene.py::test_d2_indice_fuera_de_int32_es_rechazado` (5 valores),
`::test_d2_indices_dentro_de_rango_se_aceptan` y `::test_d2_int32_maximo_llega_intacto_al_rango_de_vertices`.

---

## 8. Desviaciones aceptadas y su justificación

| # | Desviación | Veredicto |
| --- | --- | --- |
| 1 | **`Scene.mesh` es `Mesh \| None`** frente a la redacción literal de RF-08 («una malla, un esqueleto opcional…») y de T11 («`mesh` obligatorio») | **Aceptada.** RF-10 dice explícitamente que «los brazos `mesh` y `skeleton` son anulables»; el JSON Schema del diseño §3.6 ya admitía `"mesh": null` **antes** de implementar; RF-15/E-11/CA-15 exigen que el visor represente el estado vacío. Es exactamente el «punto único de cambio» preregistrado en design §3.3, ahora aplicado también a `design.md` §4.1 y registrado en `memory.md`. La clave `mesh` sigue siendo **obligatoria** en el documento (el productor la emite siempre) y `from_dict` la exige ausente≠null. No es un incumplimiento de RF-08: RF-10 prevalece sobre la enumeración de RF-08. **Recomendación de higiene:** actualizar el texto de T11 en `tasks.md`, que sigue diciendo «`mesh` obligatorio» |
| 2 | **`__all__` con 16 nombres** (T18 pedía 18; diseño §8.3 preveía 20) | **Aceptada como estado intermedio.** Los 16 son exactamente los 20 del diseño §8.3 menos `MeshStats` (T29) y `CoreStatus`/`core_status`/`expected_core_version` (T08) — los cuatro pertenecen a módulos que aún no existen, y exportarlos ahora sería imposible o mentiroso. `tests/test_layers.py::test_all_exporta_el_contrato_vigente` fija el conjunto **exacto**, de modo que la superficie no puede crecer ni menguar en silencio, y la deuda está en `memory.md`. El «18» de T18 es un error aritmético de la tarea (20 − 4 = 16); el ajuste correcto es corregir la cifra en `tasks.md`, no añadir nombres |
| 3 | `Mesh(..., normals=float64)` se acepta y se convierte a `float32`, mientras `vertices`/`joints` lo rechazan (plantilla a1/a4) | **Aceptada (leniencia documentable).** RF-08 no fija el dtype de `normals` («normales opcionales con forma (V, 3)») y la plantilla a3 solo habla de forma; `from_dict` ya entrega `float32`. Inofensiva, aunque conviene decidirla explícitamente (ver O-1) |
| 4 | Inmutabilidad «por contrato del atributo»: si el llamador muta el array que prestó, el modelo lo ve | **Aceptada y preregistrada en design §3.1.** Copiar 12 MB por malla rompería el presupuesto de RF-24; el diseño lo documenta y `mesh_from_numpy` lo advierte en su docstring. Cumple RF-08 («inmutables una vez construidas») en el sentido operativo: el modelo no expone escritura (`writeable=False`) |
| 5 | `joints` emite `0.3499999940395355` en vez de `0.35` | **Aceptada.** Consecuencia matemática de la regla «conversión `float32 → float64` exacta» del diseño §3.5. Corregirlo requeriría redondear y rompería el determinismo y la fidelidad |
| 6 | `scene_invalid_face_index.json` incluye un índice `-1` además del `9` | **Aceptada.** El esquema solo puede rechazar el negativo (`minimum: 0`); el `9` lo rechaza `from_dict`. T16 exige que la fixture falle **por las dos vías**, y así ocurre |
| 7 | `from_dict` acepta documentos sin `name` ni `metadata` (que el esquema declara obligatorios) y rechaza `schema_version: 1.0` (que el esquema acepta como `integer`) | **Aceptada como asimetría deliberada productor-estricto/consumidor-leniente** (docstring de `from_dict`). No rompe ningún round-trip; merece documentarse (O-2) |

---

## 9. Gaps y recomendaciones priorizadas

| # | Prioridad | Gap | Acción | ¿Bloquea la Fase 2? |
| --- | --- | --- | --- | --- |
| 1 | **P1** | **D-1**: malla con `F = 0` no releíble → `validate()` y round-trip fallan; el esquema y el productor dicen que es válido | Arreglar `_plano`/`_matriz_int32` para listas vacías + regresión en `test_scene.py` (`validate()` y `from_json(to_json())` con `faces=[]`) | **No.** El núcleo geométrico (T20–T32) y `py_bridge/geometry.py` consumen `Mesh` en memoria y nunca parsean JSON |
| 2 | **P1** | **D-2**: desbordamiento `int64 → int32` en índices de cara acepta `2**32`/`2**40` como índices válidos | Validar el rango antes del cast + caso `2**32` en la tabla parametrizada de invariantes | **No.** El FFI de Fase 2 recibe buffers `u32` ya validados por `Mesh`, no documentos |
| 3 | **P2** | **O-3**: `Mesh`/`Scene` heredan el `__eq__` del `@dataclass`, que revienta con `ValueError: truth value of an array … is ambiguous` al comparar dos instancias distintas | `eq=False` en las dataclasses o `field(compare=False)` en los campos `ndarray`, o implementar `__eq__` por `to_dict()` | No, pero **aparecerá en cuanto** Fase 2/3 empiece a comparar escenas en pruebas |
| 4 | **P2** | **O-4**: `test_scene_schema.py` usa `pytest.importorskip("jsonschema")`; sin el paquete, las 9 pruebas se **saltan** y la prueba automatizada de RF-12 desaparece en silencio (verificado: con un `jsonschema` roto, pytest 9 da error de colección; ausente, se saltaría) | Asegurar `jsonschema` en el entorno de CI (T06) y, opcionalmente, sustituir el `importorskip` por un import directo en `test_scene_schema.py` | No |
| 5 | **P2** | **O-5**: `ruff check .` falla con 1 `E501` preexistente en `app/main.py:263`; `ruff format --check py_bridge tests` reformatearía 4 archivos (el diseño §6.1 lo incluye como puerta de CI) | Corregir la línea y aplicar `ruff format` antes de cerrar T06/T46 | No |
| 6 | **P3** | **O-1**: dtype de `normals` no uniforme (se acepta `float64` y se convierte) | Documentarlo en el docstring o rechazarlo como `vertices`/`joints` | No |
| 7 | **P3** | **O-2**: `from_dict` acepta `name`/`metadata` ausentes pese al esquema | Decidir: endurecer, o documentar la asimetría en el docstring | No |
| 8 | **P3** | **O-6**: `pytest -m gui` selecciona 0 pruebas (89 deselected); el marcador es hoy vacuo | Instalar `pytest-qt` (T07) para que el marcador signifique algo | No |
| 9 | **P3** | Higiene de artefactos: `tasks.md` T11 dice «`mesh` obligatorio» y T18 dice «→ 18» | Corregir ambas frases en `tasks.md` (no tocar código) | No |

**Conclusión sobre el bloqueo:** ninguno de los gaps bloquea la Fase 2. El núcleo geométrico en Rust (T20–T32)
consume búferes `f32`/`u32` a través de `PyBuffer` y no depende de `Scene.from_dict`, del esquema ni de
`validate()`; la única interfaz compartida (`Mesh.faces.view(np.uint32)` y los conteos) es correcta y está
verificada. D-1 y D-2 deberían corregirse antes de la feature `mesh-import` (que sí leerá documentos externos).

---

## 10. Veredicto final

**PASS con observaciones.**

Los cinco requisitos del contrato de escena se cumplen y sus cuatro criterios de aceptación están verificados por
pruebas automatizadas y por comprobaciones independientes (determinismo en tres procesos y ocho tamaños de
troceado, esquema literal del diseño validando productor y fixtures, `parents` como fuente única, mensajes en
español con campo/esperado/recibido y sin `assert`); los dos defectos encontrados (D-1, malla sin caras no
releíble; D-2, desbordamiento de índices de cara) son acotados, tienen repro mínimo y **no bloquean** la Fase 2,
pero deben corregirse en un parche de la Fase 1 antes de aceptar documentos de escena externos.

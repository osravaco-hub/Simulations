# Verificación: `rig-studio-foundation` — Fase 2 (núcleo geométrico, T20–T32)

| Campo | Valor |
| --- | --- |
| **Feature** | `rig-studio-foundation` |
| **Alcance verificado** | Fase 2 — núcleo geométrico: `core_rust/src/{error,buffer,geometry,lib}.rs`, `core_rust/benches/`, `py_bridge/geometry.py`, `py_bridge/__init__.py`, `tests/test_geometry.py`, `tests/test_geometry_errors.py`, `tests/test_gil.py` |
| **Requisitos evaluados** | RF-19, RF-20, RF-21, RF-22, RF-23 (+ RF-26 en su parte de CA-24) |
| **Escenarios** | E-12 completo; E-06 solo en su parte de núcleo (la UI es Fase 3) |
| **Criterios** | CA-19, CA-20, CA-21, CA-22, CA-23, CA-24 |
| **Agente** | `sdd-orchestrator` (verificación propia; el subagente `sdd-verify` no tiene cuota disponible) |
| **Fecha** | 2026-11-24 |
| **Entorno** | Windows 10/11 · Python 3.15.1 · numpy 2.5.5 · pytest 9.2.0 · rustc 1.100.0 (MSVC) · maturin 1.16.0 · ruff 0.17.5 · Ryzen 3 2200U (2C/4T, 15 W, ~8 GB/s) |
| **Veredicto** | **PASS con una desviación aceptada** (CA-19 `normals`, por hardware) |

---

## 1. Resumen ejecutivo

El núcleo geométrico está completo y es correcto en todo lo que se puede medir sin discutir el
hardware: las cuatro operaciones existen con la semántica de RF-19 (incluidos los casos degenerados),
el acceso es realmente sin copia —verificado con arreglos que fallan si alguien los recorre como
secuencia y con `np.shares_memory`—, los errores llegan tipados y con mensaje accionable sin tumbar el
proceso, el GIL se libera durante el cálculo, y la línea base está registrada y es reproducible.

El único criterio no cumplido es **CA-19 para `normals`**: 47,71 ms frente a 30 ms en este equipo. El
desglose muestra que el coste es la acumulación en `f64` sobre 24 MB con escritura dispersa, un
requisito explícito de design §4.8, y que el equipo entrega ~8 GB/s de memoria. La decisión del
usuario (2026-11-24) es **mantener `f64`** y registrar la desviación; el umbral se re-basa en el
equipo objetivo antes de cerrar T44/T46.

No se han encontrado defectos bloqueantes. Hay cuatro observaciones, todas documentadas en §7.

---

## 2. Comandos ejecutados (resultados reales)

| Comando | Resultado |
| --- | --- |
| `cargo fmt --check` | exit 0 |
| `cargo clippy --all-targets -- -D warnings` | exit 0 (sin *warnings*) |
| `cargo test --no-default-features` | **21 passed**, 0 failed |
| `maturin develop --release` | wheel `core_rust-0.1.0-cp311-abi3-win_amd64.whl` instalada, exit 0 |
| `pytest -q` | **146 passed** en 5,04 s (105 de Fase 1 + 41 nuevas) |
| `pytest -q tests/test_geometry.py tests/test_geometry_errors.py tests/test_gil.py` | 41 passed |
| `ruff check .` | All checks passed |
| `cargo bench --bench geometry` (T28) | medias/medianas en `core_rust/benches/baseline.md` |

Reparto de la suite nueva: `test_geometry.py` 12 · `test_geometry_errors.py` 24 · `test_gil.py` 5.

---

## 3. Tabla RF → veredicto

| Requisito | Veredicto | Evidencia |
| --- | --- | --- |
| **RF-19** — cuatro operaciones con semántica definida | **Cumple** | `bounds` del cubo = `(-0.5,…,0.5)`; triángulo suelto → normal `(0,0,1)` unitaria; vértice sin caras y cara degenerada → `(0,0,0)` sin `NaN`; `normalize_unit_aabb` centra y lleva la mayor extensión a `[-1,1]` (y solo traslada si es nula); `mesh_stats` del cubo = `(8, 12, caja, 20.4853)` con aristas únicas (12 aristas + 6 diagonales) |
| **RF-20** — acceso sin copia | **Cumple** | Las cuatro operaciones y `py_bridge.geometry` aceptan un `ndarray` con `__getitem__`/`__len__`/`__iter__` anulados; `np.shares_memory` confirma que `as_vertices`/`as_faces_u32` no copian cuando la entrada ya cumple; preparación O(1) medida en T02 (0,70 µs con 1 M floats vs 0,80 µs con 12) |
| **RF-21** — errores tipados en la frontera | **Cumple** | 9 modos probados de forma independiente: `float64`/`int32` → `TypeError`; no contiguo, no múltiplo de 3, búfer vacío, no finitos, índice fuera de rango → `ValueError`; `int32` crudo en `faces` → `TypeError` con el remedio `faces.view(np.uint32)`. Todos nombran el argumento y el motivo; el proceso sigue vivo y el núcleo responde después |
| **RF-22** — cálculo sin retener el intérprete | **Cumple** | Prueba diferencial: durante `mesh_stats` sobre 1 M de vértices el hilo secundario hace 4,51 M de ticks en 0,65 s frente a 307 k en 0,53 s con la operación de control (ratio de tasa ≫ 5). Los cuatro adaptadores usan `py.detach` |
| **RF-23** — línea base de rendimiento | **Cumple parcialmente** | Banco criterion con 1 M de vértices / 1 996 002 caras, mediana de 10 ejecuciones tras calentamiento, registrado en `benches/baseline.md` y reproducible. `bounds` cumple (4,04 ms ≤ 15 ms); `normals` **no** (47,71 ms > 30 ms) → ver CA-19 |

---

## 4. Tabla CA → veredicto

| Criterio | Veredicto | Medición / evidencia |
| --- | --- | --- |
| **CA-19** `bounds` ≤ 15 ms y `normals` ≤ 30 ms | **NO CUMPLE (solo `normals`)** | `bounds` 4,04 ms ✅. `normals` 47,71 ms ❌ (criterion, mediana). Medición Python-side en equipo en reposo: `bounds` 4,79 ms, `normals` 58,99 ms |
| **CA-20** prueba de camino sin copia + rechazo de no conformes | **Cumple** | `SinSecuencia` en `test_geometry.py` y en la verificación propia; rechazos en `test_geometry_errors.py` |
| **CA-21** toda entrada no conforme → error tipado accionable, sin fallo nativo | **Cumple** | 24 casos en `test_geometry_errors.py` + 9 independientes; el proceso sobrevive a todos y `core_rust.add(19, 23) == 42` después |
| **CA-22** una llamada larga no bloquea un contador de Python | **Cumple** | `test_el_calculo_nativo_no_bloquea_python` (marcada `slow`) compara tasas y exige `ticks_nativo > 100 000` |
| **CA-23** `normalize_unit_aabb` no muta, no produce no finitos, cubre la extensión nula | **Cumple** | Verificación propia: entrada intacta, centro en el origen, caja `[-1,1]` en los tres ejes, y 5 vértices coincidentes → todo `(0,0,0)` finito |
| **CA-24** ≥ 8 pruebas Rust sin Python | **Cumple** | **21** pruebas en `cargo test --no-default-features` |

---

## 5. Escenarios

| Escenario | Veredicto | Nota |
| --- | --- | --- |
| **E-06** — estadísticas de 1 M de vértices sin congelar la UI | **Parcial (lo que toca a la Fase 2)** | Los valores y la no retención del intérprete están verificados (CA-22) y `bounds` cumple el umbral; `normals` no. El «la ventana sigue respondiendo» es Fase 3 (`app/workers.py`, T39–T40) |
| **E-12** — entrada no conforme al núcleo | **Cumple** | Los cuatro casos del escenario (dtype distinto, no contiguo, longitud no múltiplo de 3, índices inexistentes) producen el error correcto y el proceso continúa |

---

## 6. Comprobaciones propias (no delegadas a las pruebas del implementador)

Script externo, 52 comprobaciones, sin reutilizar código de `tests/`:

1. **Protocolo de búfer (5):** las cuatro operaciones del núcleo y `geometry.bounds` aceptan un
   `ndarray` con `__getitem__`, `__len__` e `__iter__` que lanzan; devuelven el mismo resultado que el
   arreglo normal.
2. **Formato de salida (7):** `normals` devuelve `bytes` de exactamente `12·V`; `struct.unpack("<24f")`
   coincide con `frombuffer(..., "<f4")`; la salida de `geometry.normals` es propia, escribible y no
   comparte memoria; `as_vertices` y `as_faces_u32` no copian lo que ya cumple.
3. **Semántica (14):** caja del cubo, normal de un triángulo, vértice sin caras, cara degenerada,
   unitariedad y orientación hacia fuera del cubo, `normalize` sin mutación / centrado / escala /
   extensión nula, conteos y aristas únicas de `mesh_stats`, malla sin caras y texto exacto de
   `describe()`.
4. **Errores (11):** 9 modos + supervivencia del proceso + respuesta posterior del núcleo.
5. **Determinismo (2):** dos llamadas consecutivas a `normals` y a `mesh_stats` producen resultados
   idénticos bit a bit.
6. **Rendimiento (3):** medianas con calentamiento sobre 1 M de vértices.
7. **Capas y arranque (7):** ningún archivo de `app/` importa `numpy`, `torch` ni `core_rust`; importar
   `py_bridge` no carga `torch`; `MeshStats` está en `__all__` (17 nombres); `core_rust._spike_len` ya
   no existe.

Medición de rendimiento en dos condiciones, porque la máquina estaba cargada en la primera pasada:

| Condición | `bounds` | `normals` |
| --- | --- | --- |
| criterion (T28, release, equipo en reposo) | **4,04 ms** | **47,71 ms** |
| Python-side, carga de CPU 85 % | 10,88–12,54 ms | 97,95–155,33 ms |
| Python-side, carga de CPU 12 % | **4,79 ms** | **58,99 ms** |

La dispersión demuestra que las cifras absolutas dependen del estado del equipo; el banco criterion es
la referencia. En todas las condiciones `bounds` queda por debajo de 15 ms y `normals` por encima de 30 ms.

---

## 7. Observaciones (ninguna bloqueante)

1. **O-1 — CA-19 (`normals`).** 47,71 ms vs 30 ms. Causa: acumulador `f64` de 24 MB con escritura
   dispersa (design §4.8) sobre un equipo de 15 W con ~8 GB/s. Desglose completo y alternativa `f32`
   (27,59 ms, diferencia máxima de 1 *ulp*) en `core_rust/benches/baseline.md`. **Decisión del usuario
   (2026-11-24): mantener `f64` y documentar**; re-basar el umbral en el equipo objetivo antes de
   cerrar T44/T46.
2. **O-2 — design §6.4 era inalcanzable.** La aserción `ticks_nativo > 1000 * ticks_control` supone
   que `sum(range(N))` no cede el GIL; en CPython 3.15 sí lo cede (307 k ticks). `test_gil.py` compara
   **tasas**; design §6.4 se actualizó con la medición y la justificación.
3. **O-3 — `mesh_stats` tarda 449 ms** con 2 M de caras (`HashSet` de aristas, riesgo T14 de la
   propuesta). No tiene umbral, pero **no puede llamarse desde el hilo de UI**: la Fase 3 debe usarlo
   desde `app/workers.py`. Ya está en la deuda técnica de `memory.md`.
4. **O-4 — `MeshStats.describe()` se concretó.** design §4.2 solo daba `caja [..]`; se adoptó
   `caja [min_x, min_y, min_z] → [max_x, max_y, max_z]` con 4 decimales, sin ceros sobrantes y **sin
   separadores de miles** (D-13). El texto exacto queda fijado por prueba y reflejado en design §4.2.

---

## 8. Desviaciones aceptadas y su justificación

| Desviación | Justificación |
| --- | --- |
| `normals` supera CA-19 en este equipo | Cambiar a `f32` alteraría el contrato numérico de design §4.8 por 17 ms en un equipo de gama baja; la decisión es del usuario y está registrada (2026-11-24) con la alternativa medida |
| Prueba de GIL por tasas en lugar de factor 1000× | El factor 1000× es imposible con el intérprete actual; la tasa distingue con claridad retener de liberar y sigue siendo una prueba diferencial, no estructural |
| `bounds` ya no acepta listas Python | Cambio incompatible previsto por design §4.7 y decidido en T26; ninguna llamada de `py_bridge/` lo usaba, y `py_bridge.geometry.bounds` restablece la comodidad para el usuario de Python |
| Interpretación de `describe()` | design §4.2 elidía el formato de la caja; se fijó uno explícito y se actualizó el documento |

---

## 9. Gaps y recomendaciones

1. **`cargo bench` no está en CI** (T06): el banco es manual. Añadir una ejecución periódica con
   comparación contra la línea base evitaría regresiones silenciosas en `bounds`.
2. **Re-basar CA-19** en el equipo objetivo (o en un runner de CI concreto) antes del cierre de la
   feature; hoy el veredicto depende del hardware.
3. **Vigilar `mesh_stats`**: si la Fase 3 lo llama con mallas grandes, el `HashSet` de aristas puede
   dominar el tiempo del worker; considerar reserva de capacidad o un `Vec` ordenado si aparece en el
   perfilado.
4. **T08** sigue pendiente (`CoreStatus`/`core_status`/`expected_core_version`): llevará `<py_bridge>`
   de 17 a 20 nombres y toca `tests/test_layers.py`.

---

## 10. Veredicto final

**PASS con una desviación aceptada.** RF-19, RF-20, RF-21, RF-22 y RF-23 (salvo el umbral de
`normals`) se cumplen y están demostrados con pruebas automatizadas más una verificación independiente.
CA-20, CA-21, CA-22, CA-23 y CA-24 se cumplen; CA-19 se cumple para `bounds` y queda como desviación
documentada y decidida para `normals`. La Fase 2 puede darse por cerrada a efectos de desarrollo, con
la salvedad de que T28 no se marcará como cumplida hasta re-basar CA-19 en el equipo objetivo.

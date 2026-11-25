# Línea base de rendimiento — núcleo geométrico

> Registro de T28 (RF-23 / CA-19). **Reproducible**: cualquier cambio futuro en
> `geometry.rs` debe volver a ejecutar el banco y actualizar este archivo.

## Entorno de medida

| Elemento | Valor |
| --- | --- |
| Fecha | 2026-11-20 |
| CPU | AMD Ryzen 3 2200U with Radeon Vega Mobile Gfx |
| Núcleos / hilos | 2 / 4 |
| Frecuencia nominal | 2,5 GHz (15 W, portátil) |
| Sistema | Windows (x86_64-pc-windows-msvc) |
| Compilador | `rustc 1.100.0`, `cargo bench --release` |
| Perfil | `opt-level = 3`, `lto = "thin"`, `codegen-units = 1`, `strip = "symbols"` |
| Arnés | criterion 0.5, `harness = false` |
| Parámetros | `--warm-up-time 1 --measurement-time 3 --sample-size 20` |
| Malla | 1 000 000 vértices · 1 996 002 caras (rejilla 1000×1000, altura determinista) |

Comando exacto:

```powershell
cd core_rust
cargo bench --no-default-features --bench geometry -- --warm-up-time 1 --measurement-time 3 --sample-size 20
```

`--no-default-features` desactiva `extension-module` (riesgo T9: criterion no debe
enlazar contra libpython). El banco mide **solo** las funciones puras `*_impl`.

## Resultados (mediana de 20 muestras tras calentamiento)

| Operación | Mediana | Intervalo | Umbral (CA-19) | Estado |
| --- | --- | --- | --- | --- |
| `bounds` | **4,04 ms** | 3,996 – 4,083 ms | ≤ 15 ms | ✅ cumple (3,7× de margen) |
| `normals` | **47,71 ms** | 47,27 – 48,18 ms | ≤ 30 ms | ❌ **no cumple** (1,59× por encima) |
| `normalize_unit_aabb` | 14,78 ms | 14,64 – 14,92 ms | sin umbral (diseño: 8–15 ms) | ✅ dentro de la estimación |
| `mesh_stats` | 449,24 ms | 443,9 – 455,2 ms | sin umbral (diseño: 40–120 ms) | ⚠️ 3,7× sobre la estimación (riesgo T14) |

### Desglose de `normals` (sonda instrumentada, ya eliminada)

Medido por partes sobre la misma malla, con `Instant` y mediana de 9 ejecuciones:

| Etapa | Coste | Nota |
| --- | --- | --- |
| `validate_vertices` (3 M `f32`, finitud) | 2,0 – 2,2 ms | pasada lineal |
| `validate_faces` (6 M `u32`, rango) | 1,9 – 2,1 ms | pasada lineal |
| Acumulación (2 M triángulos → 1 M `[f64; 3]`) | **25 – 28 ms** | 9 lecturas `f32` + 9 RMW `f64` por triángulo |
| Normalización (1 M vértices) | 7 – 10 ms | `sqrt` + 3 divisiones + escritura de 12 MB |
| **Total** | **43 – 48 ms** | |

Optimizaciones ya aplicadas (sin cambiar la semántica numérica de design §4.8):

- acumulador con punteros crudos y `# Safety` en lugar de indexación con *bounds check*:
  28 → 25 ms;
- normalización escribiendo sobre un `Vec<f32>` pre-dimensionado con
  `as_chunks_mut::<3>()` en vez de `push`/`extend_from_slice`: 10,4 → 7,3 ms
  (medido aislado);
- se probó el recíproco (`1/len` + multiplicación) en lugar de la división por
  componente: **sin mejora** (7,9 vs 7,3 ms) → se conserva la división exacta.

### Por qué `normals` no llega a 30 ms en este equipo

- El acumulador es `[[f64; 3]; V]` = **24 MB**, muy por encima de la caché L3
  (4 MB en este APU), y el patrón de escritura es **disperso** (3 vértices por
  cara, sin orden garantizado).
- Tráfico mínimo estimado: ~120–290 MB por llamada (vértices 12 MB + caras
  24 MB + acumulador con *read-for-ownership* ~48 MB + salida 12 MB), con
  reutilización real limitada por el tamaño del acumulador.
- Ancho de banda medido en este equipo (copia secuencial de 200 MB en `f32`):
  **8,08 GB/s**. Con ese techo, el suelo teórico del algoritmo es ~15–20 ms
  **antes** de contar los fallos de caché del acceso disperso.
- La acumulación en `f64` por vértice es un requisito explícito de design §4.8
  («acumulación en `f64` del producto cruz sin normalizar»), así que no se puede
  sustituir por `f32` (12 MB) sin cambiar el contrato numérico.

Comparación con la estimación del diseño (§4.7: 10–25 ms para `normals`): la
estimación corresponde a un equipo de escritorio con el doble o triple de ancho
de banda (DDR4 dual-channel). Este registro **no invalida** la estimación; la
sitúa en su hardware.

## `mesh_stats` (riesgo T14, sin umbral)

449 ms con 2 M de caras: dominado por el `HashSet<u64>` de aristas únicas
(~3 M inserciones, 6 M claves candidatas). Es el coste esperado del riesgo T14
del diseño («`HashSet` de aristas es el punto más caro»). Sin umbral en CA-19;
queda registrado para que la UI lo ejecute **siempre** fuera del hilo de UI
(RF-24/RF-26) y para decidir en el futuro si merece un algoritmo alternativo
(ordenación de claves) cuando exista un caso de uso real que lo exija.

## Consecuencias

1. **CA-19 queda no cumplido para `normals` en este equipo** (47,7 ms > 30 ms).
   `bounds` sí cumple con margen. Decisión pendiente del usuario/proyecto:
   - **(a)** aceptar la desviación documentada como limitación de hardware y
     re-basar en el equipo objetivo antes de dar CA-19 por cerrado;
   - **(b)** revisar el umbral de 30 ms de RF-23/CA-19;
   - **(c)** cambiar el contrato numérico de `normals` a acumulación en `f32`
     (design §4.8), lo que reduce el acumulador a 12 MB.

### Medición de la opción (c): acumulador `f32`

Variante medida con la **misma** estructura de bucle, la misma validación y el
mismo orden de sumas, cambiando solo el tipo del acumulador (sonda temporal ya
eliminada; no se modificó el código de producción):

| Variante | Mediana | Diferencia frente a producción |
| --- | --- | --- |
| `f32` acumulador (`normals_impl` actual) | 44,19 ms | — |
| `f32` acumulador en lugar de `f64` | **27,59 ms** | máx. 1,1920929e-7 por componente (1 *ulp* de `f32`) |

Es decir: la opción (c) **sí cumple CA-19 en este equipo** (27,59 ms ≤ 30 ms) y
la diferencia numérica es de un *ulp* de `f32` en la malla del banco (6 caras por
vértice). El riesgo crece en vértices con muchas caras incidentes (la cancelación
en `f32` acumula error relativo ~`N·ε`), por lo que **no se adopta sin decisión
explícita**: design §4.8 exige `f64`.
2. El umbral que sí se puede vigilar en CI es `bounds ≤ 15 ms`: es estable
   (3,99–4,08 ms) y no depende del ancho de banda.
3. `mesh_stats` no debe llamarse desde el hilo de UI sin worker (RF-24).

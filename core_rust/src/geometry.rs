//! Operaciones geométricas puras del núcleo (design §4.8).
//!
//! Nada de PyO3 aquí: todas las funciones son `*_impl` sobre rebanadas planas, de
//! modo que se prueban con `cargo test --no-default-features` (CA-24) y los
//! adaptadores de `lib.rs` solo tienen que extraer el búfer, liberar el GIL y
//! empaquetar el resultado.
//!
//! La semántica numérica es la de design §4.8 y es **vinculante**: dos
//! implementaciones independientes deben coincidir. En particular:
//!
//! - `bounds` recorre los vértices en el orden de entrada y opera en `f32`;
//! - `normals` acumula en `f64` el producto cruz sin normalizar (magnitud
//!   `2·área`) y solo al final normaliza y convierte a `f32`;
//! - `normalize_unit_aabb` centra y escala en `f64`, sin tocar la entrada;
//! - `mesh_stats` suma longitudes de arista en `f64`, cada arista no dirigida una
//!   sola vez.

use std::collections::HashSet;

use crate::error::CoreError;

/// Nombre del argumento de vértices en los mensajes de error.
const VERTICES: &str = "vertices";
/// Nombre del argumento de caras en los mensajes de error.
const FACES: &str = "faces";

/// Estadísticas de una malla (RF-19d).
#[derive(Debug, Clone, PartialEq)]
pub struct MeshStats {
    /// Número de vértices (`len(vertices) / 3`).
    pub vertex_count: usize,
    /// Número de caras (`len(faces) / 3`); puede ser 0.
    pub face_count: usize,
    /// Caja alineada a los ejes `[min_x, min_y, min_z, max_x, max_y, max_z]`.
    pub bounds: [f32; 6],
    /// Suma en `f64` de la longitud de cada arista no dirigida, una sola vez.
    pub total_edge_length: f64,
}

/// Comprueba que un búfer de vértices es utilizable.
///
/// Orden de las comprobaciones (importa para el mensaje que ve el llamador):
/// búfer no vacío, longitud múltiplo de 3 y todos los valores finitos.
fn validate_vertices(vertices: &[f32], arg: &'static str) -> Result<(), CoreError> {
    if vertices.is_empty() {
        return Err(CoreError::EmptyBuffer { arg });
    }
    if !vertices.len().is_multiple_of(3) {
        return Err(CoreError::NotMultipleOf3 {
            arg,
            len: vertices.len(),
        });
    }
    if let Some(index) = vertices.iter().position(|value| !value.is_finite()) {
        return Err(CoreError::NonFinite { arg, index });
    }
    Ok(())
}

/// Comprueba que un búfer de caras es utilizable y cabe en la malla.
///
/// Un búfer **vacío es válido** (malla sin caras, design §4.7.1). Los índices se
/// comparan con `vertex_count`, no con el rango de `u32`: el contrato de entrada
/// ya es `uint32`, así que aquí solo puede fallar la relación con `V`.
fn validate_faces(faces: &[u32], vertex_count: usize, arg: &'static str) -> Result<(), CoreError> {
    if !faces.len().is_multiple_of(3) {
        return Err(CoreError::NotMultipleOf3 {
            arg,
            len: faces.len(),
        });
    }
    for (face, triangle) in faces.as_chunks::<3>().0.iter().enumerate() {
        for (corner, &index) in triangle.iter().enumerate() {
            if index as usize >= vertex_count {
                return Err(CoreError::FaceIndexOutOfRange {
                    face,
                    corner,
                    index,
                    vertex_count,
                });
            }
        }
    }
    Ok(())
}

/// AABB de un búfer plano `[x, y, z, x, y, z, ...]` (RF-19a).
///
/// Devuelve `[min_x, min_y, min_z, max_x, max_y, max_z]`. Mínimo y máximo se
/// calculan por eje en `f32`, en el orden de entrada, para que el resultado sea
/// reproducible bit a bit.
pub fn bounds_impl(vertices: &[f32]) -> Result<[f32; 6], CoreError> {
    validate_vertices(vertices, VERTICES)?;

    let mut min = [f32::INFINITY; 3];
    let mut max = [f32::NEG_INFINITY; 3];

    for vertex in vertices.as_chunks::<3>().0 {
        for axis in 0..3 {
            min[axis] = min[axis].min(vertex[axis]);
            max[axis] = max[axis].max(vertex[axis]);
        }
    }

    Ok([min[0], min[1], min[2], max[0], max[1], max[2]])
}

/// Producto cruz `(b - a) × (c - a)` de una cara, sin normalizar.
///
/// La magnitud es `2·área`, así que acumularlo por vértice da el promedio
/// ponderado por área que pide RF-19b. Se calcula en `f32` (design §4.8) y se
/// acumula en `f64` en [`normals_impl`].
fn face_normal(a: [f32; 3], b: [f32; 3], c: [f32; 3]) -> [f32; 3] {
    let ab = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
    let ac = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
    [
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    ]
}

/// Una normal por vértice, acumulada por área y normalizada (RF-19b).
///
/// Recorre las caras en orden, suma en `f64` el producto cruz sin normalizar de
/// cada cara incidente y, al final, normaliza y convierte a `f32`. Un vértice sin
/// caras, con caras degeneradas o con suma simétrica nula devuelve
/// `(0.0, 0.0, 0.0)`; nunca `NaN` ni infinito.
///
/// Un búfer de caras vacío es válido: devuelve `(V, 3)` de ceros.
pub fn normals_impl(vertices: &[f32], faces: &[u32]) -> Result<Vec<f32>, CoreError> {
    validate_vertices(vertices, VERTICES)?;
    let points = vertices.as_chunks::<3>().0;
    validate_faces(faces, points.len(), FACES)?;

    let mut accumulated = vec![[0.0_f64; 3]; points.len()];
    for triangle in faces.as_chunks::<3>().0 {
        // SAFETY: `validate_faces(faces, points.len(), …)` ya se ejecutó arriba y
        // garantiza, para **toda** esquina de **toda** cara, `index < points.len()`
        // (y por tanto `< accumulated.len()`). Se usan punteros crudos en lugar de
        // `&mut` para no afirmar exclusividad: una cara degenerada puede repetir
        // índice, y dos `&mut` al mismo elemento serían *aliasing* (UB). El orden de
        // las sumas es el de las caras, así que el resultado sigue siendo
        // reproducible bit a bit.
        let (a, b, c) = unsafe {
            (
                *points.get_unchecked(triangle[0] as usize),
                *points.get_unchecked(triangle[1] as usize),
                *points.get_unchecked(triangle[2] as usize),
            )
        };
        let normal = face_normal(a, b, c);
        let (nx, ny, nz) = (
            f64::from(normal[0]),
            f64::from(normal[1]),
            f64::from(normal[2]),
        );
        unsafe {
            for &index in triangle {
                // Puntero crudo, no `&mut`: una cara degenerada puede repetir
                // índice y dos `&mut` al mismo elemento serían *aliasing* (UB).
                let slot = &mut *accumulated.as_mut_ptr().add(index as usize);
                slot[0] += nx;
                slot[1] += ny;
                slot[2] += nz;
            }
        }
    }

    // Se escribe directamente sobre un búfer del tamaño final: `push` por
    // componente costaba ~10 ms en 1M de vértices solo en comprobaciones de
    // capacidad y memcpy de 12 bytes.
    let mut normals = vec![0.0_f32; vertices.len()];
    for (vertex, sum) in normals.as_chunks_mut::<3>().0.iter_mut().zip(&accumulated) {
        let length = (sum[0] * sum[0] + sum[1] * sum[1] + sum[2] * sum[2]).sqrt();
        if length > 0.0 && length.is_finite() {
            // Vértice aislado, caras degeneradas o suma cancelada: queda el cero
            // exacto con el que se inicializó el búfer.
            *vertex = [
                (sum[0] / length) as f32,
                (sum[1] / length) as f32,
                (sum[2] / length) as f32,
            ];
        }
    }
    Ok(normals)
}

/// Vértices trasladados al origen de su caja y escalados a `[-1, 1]` (RF-19c).
///
/// `centro = (min + max) / 2` y `ext = max(max_i − min_i)`. Si `ext <= 0` (todos
/// los vértices coinciden) solo se traslada, con escala 1; si no, cada
/// coordenada se multiplica por `2 / ext`. El cálculo intermedio es `f64` y el
/// resultado `f32`. La entrada **no se modifica**.
pub fn normalize_unit_aabb_impl(vertices: &[f32]) -> Result<Vec<f32>, CoreError> {
    validate_vertices(vertices, VERTICES)?;
    let [min_x, min_y, min_z, max_x, max_y, max_z] = bounds_impl(vertices)?;

    let center = [
        (f64::from(min_x) + f64::from(max_x)) / 2.0,
        (f64::from(min_y) + f64::from(max_y)) / 2.0,
        (f64::from(min_z) + f64::from(max_z)) / 2.0,
    ];
    let extents = [
        f64::from(max_x) - f64::from(min_x),
        f64::from(max_y) - f64::from(min_y),
        f64::from(max_z) - f64::from(min_z),
    ];
    let extent = extents[0].max(extents[1]).max(extents[2]);
    let scale = if extent > 0.0 { 2.0 / extent } else { 1.0 };

    let mut normalized = Vec::with_capacity(vertices.len());
    for vertex in vertices.as_chunks::<3>().0 {
        for axis in 0..3 {
            normalized.push(((f64::from(vertex[axis]) - center[axis]) * scale) as f32);
        }
    }
    Ok(normalized)
}

/// Clave no dirigida de una arista: `(min << 32) | max`.
fn edge_key(a: u32, b: u32) -> u64 {
    let (low, high) = if a <= b { (a, b) } else { (b, a) };
    (u64::from(low) << 32) | u64::from(high)
}

/// Longitud euclídea entre dos vértices, en `f64`.
fn distance(a: [f32; 3], b: [f32; 3]) -> f64 {
    let dx = f64::from(b[0]) - f64::from(a[0]);
    let dy = f64::from(b[1]) - f64::from(a[1]);
    let dz = f64::from(b[2]) - f64::from(a[2]);
    (dx * dx + dy * dy + dz * dz).sqrt()
}

/// Suma la longitud de cada arista **no dirigida** una sola vez (RF-19d).
///
/// La tabla de aristas se dimensiona a `3F/2` (`len(faces) / 2`) como anticipo de
/// `HashSet` sin rehash: con mallas grandes el coste dominante es el hash, no la
/// geometría (riesgo T14). La suma es en `f64` y en el orden de las caras, para
/// que el resultado sea reproducible.
fn unique_edge_length(vertices: &[f32], faces: &[u32]) -> f64 {
    let points = vertices.as_chunks::<3>().0;
    let mut seen: HashSet<u64> = HashSet::with_capacity(faces.len() / 2);
    let mut total = 0.0_f64;

    for triangle in faces.as_chunks::<3>().0 {
        let pairs = [
            (triangle[0], triangle[1]),
            (triangle[1], triangle[2]),
            (triangle[2], triangle[0]),
        ];
        for (a, b) in pairs {
            if seen.insert(edge_key(a, b)) {
                total += distance(points[a as usize], points[b as usize]);
            }
        }
    }
    total
}

/// Estadísticas de malla: conteos, caja y longitud total de aristas (RF-19d).
///
/// Reutiliza [`bounds_impl`] para que la caja sea idéntica a la de `bounds`. Un
/// búfer de caras vacío es válido: `face_count = 0` y `total_edge_length = 0.0`.
pub fn mesh_stats_impl(vertices: &[f32], faces: &[u32]) -> Result<MeshStats, CoreError> {
    validate_vertices(vertices, VERTICES)?;
    let vertex_count = vertices.len() / 3;
    validate_faces(faces, vertex_count, FACES)?;

    Ok(MeshStats {
        vertex_count,
        face_count: faces.len() / 3,
        bounds: bounds_impl(vertices)?,
        total_edge_length: unique_edge_length(vertices, faces),
    })
}

#[cfg(test)]
mod tests {
    use super::{CoreError, bounds_impl, mesh_stats_impl, normalize_unit_aabb_impl, normals_impl};

    /// Vértices del cubo unidad de `[-1, 1]³`.
    const CUBO: [f32; 24] = [
        -1.0, -1.0, -1.0, //
        1.0, -1.0, -1.0, //
        1.0, 1.0, -1.0, //
        -1.0, 1.0, -1.0, //
        -1.0, -1.0, 1.0, //
        1.0, -1.0, 1.0, //
        1.0, 1.0, 1.0, //
        -1.0, 1.0, 1.0,
    ];

    /// 12 triángulos con las normales hacia fuera (regla de la mano derecha).
    const CARAS_CUBO: [u32; 36] = [
        0, 2, 1, 0, 3, 2, // z = -1
        4, 5, 6, 4, 6, 7, // z = +1
        0, 1, 5, 0, 5, 4, // y = -1
        3, 7, 6, 3, 6, 2, // y = +1
        0, 4, 7, 0, 7, 3, // x = -1
        1, 2, 6, 1, 6, 5, // x = +1
    ];

    fn approx(a: f32, b: f32) -> bool {
        (a - b).abs() < 1e-6
    }

    #[test]
    fn bounds_cubo_unidad() {
        assert_eq!(
            bounds_impl(&CUBO).expect("el cubo es válido"),
            [-1.0, -1.0, -1.0, 1.0, 1.0, 1.0]
        );
    }

    #[test]
    fn bounds_buffer_vacio_es_error() {
        assert_eq!(
            bounds_impl(&[]),
            Err(CoreError::EmptyBuffer { arg: "vertices" })
        );
    }

    #[test]
    fn bounds_longitud_no_multiplo_de_3() {
        assert_eq!(
            bounds_impl(&[0.0, 1.0]),
            Err(CoreError::NotMultipleOf3 {
                arg: "vertices",
                len: 2
            })
        );
    }

    #[test]
    fn bounds_rechaza_valores_no_finitos() {
        let mut vertices = CUBO;
        vertices[4] = f32::NAN;
        assert_eq!(
            bounds_impl(&vertices),
            Err(CoreError::NonFinite {
                arg: "vertices",
                index: 4
            })
        );

        vertices[4] = f32::INFINITY;
        assert_eq!(
            bounds_impl(&vertices),
            Err(CoreError::NonFinite {
                arg: "vertices",
                index: 4
            })
        );
    }

    #[test]
    fn normals_cubo_apunta_hacia_fuera() {
        let normals = normals_impl(&CUBO, &CARAS_CUBO).expect("el cubo es válido");
        assert_eq!(normals.len(), 8 * 3);

        for (vertex, normal) in CUBO
            .as_chunks::<3>()
            .0
            .iter()
            .zip(normals.as_chunks::<3>().0)
        {
            let length =
                (normal[0] * normal[0] + normal[1] * normal[1] + normal[2] * normal[2]).sqrt();
            assert!(
                approx(length, 1.0),
                "la normal debe ser unitaria: {normal:?}"
            );

            // En un cubo centrado, la normal de una esquina apunta en la misma
            // dirección que el propio vértice (diagonal exterior).
            let dot = vertex[0] * normal[0] + vertex[1] * normal[1] + vertex[2] * normal[2];
            assert!(dot > 0.99, "la normal debe apuntar hacia fuera: {normal:?}");
        }
    }

    #[test]
    fn normals_vertice_aislado_es_cero() {
        // Triángulo en el plano z = 0 más un cuarto vértice que ninguna cara usa.
        let vertices = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 5.0, 5.0, 5.0];
        let faces = [0, 1, 2];
        let normals = normals_impl(&vertices, &faces).expect("la malla es válida");

        assert_eq!(normals.len(), 12);
        assert_eq!(&normals[9..], &[0.0, 0.0, 0.0]);
        assert_eq!(&normals[0..3], &[0.0, 0.0, 1.0]);
    }

    #[test]
    fn normals_indice_fuera_de_rango() {
        let faces = [0, 1, 8];
        assert_eq!(
            normals_impl(&CUBO, &faces),
            Err(CoreError::FaceIndexOutOfRange {
                face: 0,
                corner: 2,
                index: 8,
                vertex_count: 8,
            })
        );
    }

    #[test]
    fn normals_cara_degenerada_no_produce_nan() {
        let vertices = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0];
        let faces = [0, 1, 2];
        let normals = normals_impl(&vertices, &faces).expect("la malla es válida");

        assert_eq!(normals, vec![0.0; 9]);
        assert!(normals.iter().all(|value| value.is_finite()));
    }

    #[test]
    fn normals_malla_sin_caras_devuelve_ceros() {
        let normals = normals_impl(&CUBO, &[]).expect("una malla sin caras es válida");
        assert_eq!(normals, vec![0.0; 24]);
    }

    #[test]
    fn normals_rechaza_longitud_de_caras_no_multiplo_de_3() {
        assert_eq!(
            normals_impl(&CUBO, &[0, 1]),
            Err(CoreError::NotMultipleOf3 {
                arg: "faces",
                len: 2
            })
        );
    }

    #[test]
    fn normalize_centra_y_escala_a_unidad() {
        // Caja de (0,0,0) a (2,4,6): centro (1,2,3), extensión máxima 6.
        let vertices = [0.0, 0.0, 0.0, 2.0, 0.0, 0.0, 0.0, 4.0, 0.0, 0.0, 0.0, 6.0];
        let normalized = normalize_unit_aabb_impl(&vertices).expect("la malla es válida");
        let caja = bounds_impl(&normalized).expect("el resultado es válido");

        assert!(approx(caja[0], -1.0 / 3.0) && approx(caja[3], 1.0 / 3.0));
        assert!(approx(caja[1], -2.0 / 3.0) && approx(caja[4], 2.0 / 3.0));
        assert!(approx(caja[2], -1.0) && approx(caja[5], 1.0));
    }

    #[test]
    fn normalize_no_modifica_entrada() {
        let vertices = [
            0.0_f32, 0.0, 0.0, 2.0, 0.0, 0.0, 0.0, 4.0, 0.0, 0.0, 0.0, 6.0,
        ];
        let original = vertices;
        let _ = normalize_unit_aabb_impl(&vertices).expect("la malla es válida");
        assert_eq!(vertices, original);
    }

    #[test]
    fn normalize_extent_nula_no_escala() {
        let vertices = [1.5_f32, -2.0, 3.25, 1.5, -2.0, 3.25, 1.5, -2.0, 3.25];
        let normalized = normalize_unit_aabb_impl(&vertices).expect("la malla es válida");

        assert_eq!(normalized.len(), vertices.len());
        assert!(normalized.iter().all(|value| *value == 0.0));
        assert!(normalized.iter().all(|value| value.is_finite()));
    }

    #[test]
    fn normalize_rechaza_valores_no_finitos() {
        assert_eq!(
            normalize_unit_aabb_impl(&[0.0, 0.0, f32::NAN]),
            Err(CoreError::NonFinite {
                arg: "vertices",
                index: 2
            })
        );
    }

    #[test]
    fn mesh_stats_cuenta_aristas_unicas() {
        let stats = mesh_stats_impl(&CUBO, &CARAS_CUBO).expect("el cubo es válido");

        assert_eq!(stats.vertex_count, 8);
        assert_eq!(stats.face_count, 12);
        // 12 aristas de cubo de longitud 2 + 6 diagonales de cara de 2·√2.
        let esperado = 12.0 * 2.0 + 6.0 * 2.0 * 2.0_f64.sqrt();
        assert!(
            (stats.total_edge_length - esperado).abs() < 1e-9,
            "{} != {esperado}",
            stats.total_edge_length
        );
    }

    #[test]
    fn mesh_stats_bounds_coincide_con_bounds() {
        let stats = mesh_stats_impl(&CUBO, &CARAS_CUBO).expect("el cubo es válido");
        assert_eq!(stats.bounds, bounds_impl(&CUBO).expect("el cubo es válido"));
    }

    #[test]
    fn mesh_stats_malla_sin_caras() {
        let stats = mesh_stats_impl(&CUBO, &[]).expect("una malla sin caras es válida");

        assert_eq!(stats.vertex_count, 8);
        assert_eq!(stats.face_count, 0);
        assert_eq!(stats.total_edge_length, 0.0);
        assert_eq!(stats.bounds, [-1.0, -1.0, -1.0, 1.0, 1.0, 1.0]);
    }
}

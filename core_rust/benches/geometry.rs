//! Banco de rendimiento del núcleo geométrico (T28, RF-23 / CA-19).
//!
//! Mide **solo funciones puras** (`geometry::*_impl`) sobre una malla sintética
//! de un millón de vértices y ~2 millones de caras. Nunca toca PyO3 ni el
//! protocolo de búfer, de modo que se ejecuta con `--no-default-features` y no
//! depende de `extension-module` (riesgo T9):
//!
//! ```text
//! cargo bench --no-default-features --bench geometry
//! ```
//!
//! Umbrales de la especificación (RF-23 / CA-19): `bounds` ≤ 15 ms y `normals`
//! ≤ 30 ms. `mesh_stats` no tiene umbral; su coste se anota en `baseline.md`
//! (riesgo T14).
//!
//! La malla es una rejilla de `SIDE × SIDE` vértices con altura determinista
//! (`sin·cos` en `f32`): 1 000 000 de vértices y 1 996 002 caras, con índices
//! siempre válidos y triángulos no degenerados.

use std::hint::black_box;

use core_rust::geometry::{bounds_impl, mesh_stats_impl, normalize_unit_aabb_impl, normals_impl};
use criterion::{Criterion, criterion_group, criterion_main};

/// Lado de la rejilla: `SIDE²` vértices.
const SIDE: usize = 1000;

/// Construye la malla sintética del banco: `(vertices, caras)`.
///
/// `vertices` es plano `[x, y, z, ...]` con `SIDE²` tripletas; `faces` son dos
/// triángulos por celda de la rejilla, en `(i0, i2, i1)` / `(i1, i2, i3)` para
/// que el producto cruz apunte siempre hacia el mismo lado.
fn malla_sintetica() -> (Vec<f32>, Vec<u32>) {
    let mut vertices = Vec::with_capacity(SIDE * SIDE * 3);
    for row in 0..SIDE {
        for col in 0..SIDE {
            let x = col as f32 * 0.01;
            let y = row as f32 * 0.01;
            // Altura determinista: misma malla en cada ejecución del banco.
            let z = (x * 0.5).sin() * (y * 0.5).cos();
            vertices.extend_from_slice(&[x, y, z]);
        }
    }

    let celdas = SIDE - 1;
    let mut faces = Vec::with_capacity(celdas * celdas * 6);
    for row in 0..celdas {
        for col in 0..celdas {
            let i0 = (row * SIDE + col) as u32;
            let i1 = i0 + 1;
            let i2 = i0 + SIDE as u32;
            let i3 = i2 + 1;
            faces.extend_from_slice(&[i0, i2, i1, i1, i2, i3]);
        }
    }

    (vertices, faces)
}

fn banco(c: &mut Criterion) {
    let (vertices, faces) = malla_sintetica();
    println!(
        "malla del banco: {} vértices · {} caras",
        vertices.len() / 3,
        faces.len() / 3
    );

    let mut group = c.benchmark_group("geometry");

    group.bench_function("bounds", |b| {
        b.iter(|| {
            black_box(bounds_impl(black_box(vertices.as_slice())).expect("malla válida"));
        });
    });

    group.bench_function("normals", |b| {
        b.iter(|| {
            black_box(
                normals_impl(black_box(vertices.as_slice()), black_box(faces.as_slice()))
                    .expect("malla válida"),
            );
        });
    });

    group.bench_function("normalize_unit_aabb", |b| {
        b.iter(|| {
            black_box(
                normalize_unit_aabb_impl(black_box(vertices.as_slice())).expect("malla válida"),
            );
        });
    });

    // Sin umbral en CA-19: se mide para documentar el coste del `HashSet`
    // (riesgo T14).
    group.bench_function("mesh_stats", |b| {
        b.iter(|| {
            black_box(
                mesh_stats_impl(black_box(vertices.as_slice()), black_box(faces.as_slice()))
                    .expect("malla válida"),
            );
        });
    });

    group.finish();
}

criterion_group!(benches, banco);
criterion_main!(benches);

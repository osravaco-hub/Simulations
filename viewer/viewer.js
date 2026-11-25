/**
 * Visor 3D de Rig Studio — demo mínima con three.js (UMD r149).
 *
 * Contenido: cubo girando sobre una rejilla, cámara en perspectiva con órbita
 * básica (arrastrar + rueda) y una API `window.RigViewer` que la app Python
 * puede invocar con `page().runJavaScript(...)`.
 *
 * Nota de arquitectura: este archivo es un script clásico (no un módulo ES)
 * porque se carga desde file://. Cuando llegue la feature `viewer-3d`
 * (WebGL vendorizado con ES modules y esquema Qt propio) se migrará.
 */

(function () {
  "use strict";

  const canvas = document.getElementById("viewport");
  const fpsEl = document.getElementById("fps");
  const engineEl = document.getElementById("engine");
  const errorEl = document.getElementById("error");

  function fail(message) {
    errorEl.hidden = false;
    errorEl.textContent = message;
    console.error(message);
  }

  if (!window.THREE) {
    fail("three.js no se pudo cargar (falta viewer/vendor/three.min.js).");
    return;
  }

  const THREE = window.THREE;
  engineEl.textContent = "three.js r" + THREE.REVISION;

  // Diagnóstico de contexto: si la página se abrió en un navegador (no dentro de
  // la app), avisamos de que no habrá paneles laterales. Confusión frecuente.
  const modeEl = document.getElementById("mode");
  const embedded =
    /QtWebEngine/i.test(navigator.userAgent) || typeof window.qt !== "undefined";
  if (!embedded && modeEl) {
    modeEl.hidden = false;
    modeEl.textContent = "vista previa web: sin paneles · abre la app con python -m app.main";
  }
  console.info("[viewer] contexto:", embedded ? "QtWebEngine" : "navegador");

  // ---------------------------------------------------------------- escena
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0e1116);
  scene.fog = new THREE.Fog(0x0e1116, 7, 20);

  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
  const CAMERA_HOME = new THREE.Vector3(2.8, 2.2, 3.6);
  camera.position.copy(CAMERA_HOME);
  camera.lookAt(0, 0, 0);

  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputEncoding = THREE.sRGBEncoding; // API de r149
  } catch (err) {
    fail("WebGL no disponible en este equipo.\n" + err.message);
    return;
  }

  // ---------------------------------------------------------------- luces
  scene.add(new THREE.HemisphereLight(0x8fb8dd, 0x0a0e14, 1.15));

  const keyLight = new THREE.DirectionalLight(0xffffff, 1.7);
  keyLight.position.set(4, 6, 3);
  scene.add(keyLight);

  const fillLight = new THREE.DirectionalLight(0x4cc9f0, 0.55);
  fillLight.position.set(-4, 2, -3);
  scene.add(fillLight);

  // ---------------------------------------------------------------- cubo
  const geometry = new THREE.BoxGeometry(1.4, 1.4, 1.4);
  const material = new THREE.MeshStandardMaterial({
    color: 0x4cc9f0,
    metalness: 0.25,
    roughness: 0.35,
  });

  const cube = new THREE.Mesh(geometry, material);
  cube.add(
    new THREE.LineSegments(
      new THREE.EdgesGeometry(geometry),
      new THREE.LineBasicMaterial({ color: 0xbfefff, transparent: true, opacity: 0.5 })
    )
  );
  cube.position.y = 0.2;
  scene.add(cube);

  // Rejilla de referencia
  const grid = new THREE.GridHelper(12, 12, 0x2b3746, 0x1b2430);
  grid.position.y = -0.75;
  scene.add(grid);

  // ---------------------------------------------------------------- órbita
  const orbit = { radius: CAMERA_HOME.length(), theta: 0.65, phi: 0.42, dragging: false, lastX: 0, lastY: 0 };

  function applyOrbit() {
    const r = orbit.radius;
    camera.position.set(
      r * Math.cos(orbit.phi) * Math.sin(orbit.theta),
      r * Math.sin(orbit.phi),
      r * Math.cos(orbit.phi) * Math.cos(orbit.theta)
    );
    camera.lookAt(0, 0.2, 0);
  }

  orbit.radius = CAMERA_HOME.length();
  orbit.theta = Math.atan2(CAMERA_HOME.x, CAMERA_HOME.z);
  orbit.phi = Math.asin(CAMERA_HOME.y / orbit.radius);
  applyOrbit();

  canvas.addEventListener("pointerdown", function (event) {
    orbit.dragging = true;
    orbit.lastX = event.clientX;
    orbit.lastY = event.clientY;
    canvas.setPointerCapture(event.pointerId);
  });

  canvas.addEventListener("pointermove", function (event) {
    if (!orbit.dragging) return;
    orbit.theta -= (event.clientX - orbit.lastX) * 0.008;
    orbit.phi = Math.max(-1.2, Math.min(1.35, orbit.phi + (event.clientY - orbit.lastY) * 0.006));
    orbit.lastX = event.clientX;
    orbit.lastY = event.clientY;
    applyOrbit();
  });

  canvas.addEventListener("pointerup", function () {
    orbit.dragging = false;
  });

  canvas.addEventListener(
    "wheel",
    function (event) {
      event.preventDefault();
      orbit.radius = Math.max(2.2, Math.min(14, orbit.radius * (event.deltaY > 0 ? 1.08 : 0.92)));
      applyOrbit();
    },
    { passive: false }
  );

  // ---------------------------------------------------------------- bucle
  const clock = new THREE.Clock();
  let paused = false;
  let frames = 0;
  let fpsTimer = 0;

  function resize() {
    const width = canvas.clientWidth || 1;
    const height = canvas.clientHeight || 1;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }

  new ResizeObserver(resize).observe(canvas);
  resize();

  function animate() {
    requestAnimationFrame(animate);

    const delta = clock.getDelta();

    if (!paused) {
      cube.rotation.y += delta * 0.6;
      cube.rotation.x += delta * 0.15;
    }

    renderer.render(scene, camera);

    frames += 1;
    fpsTimer += delta;
    if (fpsTimer >= 0.5) {
      fpsEl.textContent = Math.round(frames / fpsTimer) + " fps";
      frames = 0;
      fpsTimer = 0;
    }
  }

  animate();

  // ---------------------------------------------------------------- API
  window.RigViewer = {
    isReady: true,
    threeRevision: THREE.REVISION,

    /** Cambia el color del material del cubo (0xRRGGBB o "#rrggbb"). */
    setCubeColor: function (color) {
      cube.material.color.set(color);
    },

    /** Devuelve la cámara a su posición inicial. */
    resetCamera: function () {
      orbit.radius = CAMERA_HOME.length();
      orbit.theta = Math.atan2(CAMERA_HOME.x, CAMERA_HOME.z);
      orbit.phi = Math.asin(CAMERA_HOME.y / orbit.radius);
      applyOrbit();
    },

    /** Pausa/reanuda la rotación del cubo. */
    setPaused: function (value) {
      paused = Boolean(value);
      return paused;
    },

    /**
     * Reservado: la escena real (malla + esqueleto) llegará con el canal
     * app→visor. Hoy solo avisa para que la UI no falle en silencio.
     */
    setScene: function (sceneData) {
      console.warn("[viewer] setScene() pendiente (T36); demo de cubo activa.", sceneData || null);
      return false;
    },

    clear: function () {
      this.setScene(null);
    },

    isPaused: function () {
      return paused;
    },

    info: function () {
      return {
        revision: THREE.REVISION,
        vertices: cube.geometry.attributes.position.count,
        paused: paused,
      };
    },
  };

  window.dispatchEvent(new CustomEvent("rigviewer-ready", { detail: window.RigViewer.info() }));
  console.info("[viewer] listo · three.js r" + THREE.REVISION);
})();

/**
 * Shared Three.js 3D model viewer — used by Nodes and Gallery pages.
 * Three.js is loaded locally from /static/js/vendor/three/ via import map.
 * Supports OBJ, GLB/GLTF, STL.
 */

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/OrbitControls.js';
import { OBJLoader } from 'three/addons/OBJLoader.js';
import { GLTFLoader } from 'three/addons/GLTFLoader.js';
import { STLLoader } from 'three/addons/STLLoader.js';

const t = (key) => window.GhostI18n?.t(key) ?? key;

export const MODEL_EXTS = ['obj', 'glb', 'gltf', 'stl'];

export function isModelExt(ext) {
  return MODEL_EXTS.includes((ext || '').toLowerCase());
}

export function render3DScene(container, src, ext) {
  const w = container.clientWidth, h = container.clientHeight;

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x1a1a2e);

  const camera = new THREE.PerspectiveCamera(50, w / h, 0.01, 1000);
  camera.position.set(0, 1, 3);

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(w, h);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.2;
  container.innerHTML = '';
  container.appendChild(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.autoRotate = true;
  controls.autoRotateSpeed = 2.0;

  const ambient = new THREE.AmbientLight(0xffffff, 0.6);
  scene.add(ambient);
  const dirLight = new THREE.DirectionalLight(0xffffff, 1.0);
  dirLight.position.set(5, 10, 7);
  scene.add(dirLight);
  const backLight = new THREE.DirectionalLight(0x8888ff, 0.4);
  backLight.position.set(-5, -3, -5);
  scene.add(backLight);

  const grid = new THREE.GridHelper(4, 20, 0x333355, 0x222244);
  scene.add(grid);

  function fitCamera(object) {
    const box = new THREE.Box3().setFromObject(object);
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z);
    const dist = maxDim * 2;
    object.position.sub(center);
    camera.position.set(dist * 0.6, dist * 0.5, dist * 0.8);
    controls.target.set(0, 0, 0);
    controls.update();
  }

  function applyDefaultMaterial(object) {
    const mat = new THREE.MeshStandardMaterial({
      color: 0x8888cc, metalness: 0.3, roughness: 0.6,
      side: THREE.DoubleSide,
    });
    object.traverse((child) => {
      if (child.isMesh) {
        if (!child.material || !child.material.map) child.material = mat;
        child.castShadow = true;
        child.receiveShadow = true;
      }
    });
  }

  function onLoad(object) {
    applyDefaultMaterial(object);
    scene.add(object);
    fitCamera(object);
  }

  const lowerExt = (ext || '').toLowerCase();
  if (lowerExt === 'obj') {
    new OBJLoader().load(src, onLoad);
  } else if (lowerExt === 'glb' || lowerExt === 'gltf') {
    new GLTFLoader().load(src, (gltf) => { scene.add(gltf.scene); fitCamera(gltf.scene); });
  } else if (lowerExt === 'stl') {
    new STLLoader().load(src, (geometry) => {
      const mat = new THREE.MeshStandardMaterial({ color: 0x8888cc, metalness: 0.3, roughness: 0.6, side: THREE.DoubleSide });
      const mesh = new THREE.Mesh(geometry, mat);
      scene.add(mesh);
      fitCamera(mesh);
    });
  }

  let animId;
  function animate() {
    animId = requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  }
  animate();

  const ro = new ResizeObserver(() => {
    const nw = container.clientWidth, nh = container.clientHeight;
    if (nw > 0 && nh > 0) {
      camera.aspect = nw / nh;
      camera.updateProjectionMatrix();
      renderer.setSize(nw, nh);
    }
  });
  ro.observe(container);

  return {
    dispose() {
      cancelAnimationFrame(animId);
      ro.disconnect();
      controls.dispose();
      renderer.dispose();
      scene.traverse((obj) => {
        if (obj.geometry) obj.geometry.dispose();
        if (obj.material) {
          if (Array.isArray(obj.material)) obj.material.forEach(m => m.dispose());
          else obj.material.dispose();
        }
      });
    }
  };
}

export function renderPreview(container, src, ext) {
  try {
    return render3DScene(container, src, ext);
  } catch (e) {
    container.innerHTML = `<div class="flex items-center justify-center h-full text-zinc-500 text-xs">${t('nodes.3dLoadError')}</div>`;
    return null;
  }
}

export function openFullscreen(src, ext) {
  const existing = document.getElementById('three-viewer-overlay');
  if (existing) existing.remove();

  const overlay = document.createElement('div');
  overlay.id = 'three-viewer-overlay';
  overlay.style.cssText = 'position:fixed;inset:0;z-index:120;background:rgba(0,0,0,0.92);display:flex;flex-direction:column;align-items:center;justify-content:center';
  overlay.innerHTML = `
    <div id="three-fs-canvas" style="width:90vw;height:80vh;border-radius:12px;overflow:hidden;border:1px solid rgba(255,255,255,0.1)"></div>
    <div style="display:flex;gap:8px;margin-top:12px">
      <a href="${src}" download class="text-xs text-zinc-400 hover:text-white bg-black/60 px-3 py-1.5 rounded-full transition-colors">${t('nodes.download')}</a>
      <button id="three-fs-close" class="text-xs text-zinc-400 hover:text-white bg-black/60 px-3 py-1.5 rounded-full transition-colors">${t('nodes.close')}</button>
    </div>`;
  document.body.appendChild(overlay);

  let sceneHandle = null;
  try {
    sceneHandle = render3DScene(overlay.querySelector('#three-fs-canvas'), src, ext);
  } catch (e) {
    overlay.querySelector('#three-fs-canvas').innerHTML = `<div class="flex items-center justify-center h-full text-red-400 text-sm">${t('nodes.3dLoadError')}</div>`;
  }

  function closeViewer() {
    if (sceneHandle) sceneHandle.dispose();
    overlay.remove();
    document.removeEventListener('keydown', onKey);
  }
  function onKey(e) { if (e.key === 'Escape') closeViewer(); }
  document.addEventListener('keydown', onKey);
  overlay.querySelector('#three-fs-close')?.addEventListener('click', closeViewer);
}

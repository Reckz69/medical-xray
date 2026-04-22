"use client";

import { useRef, useMemo } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Sphere, MeshDistortMaterial, Float, TorusKnot, Ring } from "@react-three/drei";
import * as THREE from "three";

/* ---- Floating anatomical lung-like mesh ---- */
function LungMesh() {
  const leftRef = useRef<THREE.Mesh>(null!);
  const rightRef = useRef<THREE.Mesh>(null!);

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    // Breathing simulation
    const breathe = 1 + Math.sin(t * 1.2) * 0.04;
    leftRef.current.scale.set(breathe, breathe, breathe);
    rightRef.current.scale.set(breathe, breathe, breathe);
    leftRef.current.rotation.y = Math.sin(t * 0.3) * 0.08;
    rightRef.current.rotation.y = -Math.sin(t * 0.3) * 0.08;
  });

  return (
    <group>
      {/* Left Lung */}
      <mesh ref={leftRef} position={[-0.85, 0, 0]}>
        <sphereGeometry args={[0.72, 32, 32]} />
        <MeshDistortMaterial
          color="#16a34a"
          roughness={0.15}
          metalness={0.1}
          distort={0.35}
          speed={2}
          transparent
          opacity={0.85}
        />
      </mesh>

      {/* Right Lung */}
      <mesh ref={rightRef} position={[0.85, 0, 0]}>
        <sphereGeometry args={[0.72, 32, 32]} />
        <MeshDistortMaterial
          color="#15803d"
          roughness={0.15}
          metalness={0.1}
          distort={0.35}
          speed={2.4}
          transparent
          opacity={0.85}
        />
      </mesh>

      {/* Trachea / center connector */}
      <mesh position={[0, 0.5, 0]}>
        <cylinderGeometry args={[0.09, 0.09, 0.8, 12]} />
        <meshStandardMaterial color="#4ade80" roughness={0.3} metalness={0.15} transparent opacity={0.7} />
      </mesh>

      {/* Branching bronchi - left */}
      <mesh position={[-0.42, 0.08, 0]} rotation={[0, 0, Math.PI / 4.5]}>
        <cylinderGeometry args={[0.06, 0.06, 0.7, 10]} />
        <meshStandardMaterial color="#4ade80" roughness={0.3} metalness={0.15} transparent opacity={0.7} />
      </mesh>

      {/* Branching bronchi - right */}
      <mesh position={[0.42, 0.08, 0]} rotation={[0, 0, -Math.PI / 4.5]}>
        <cylinderGeometry args={[0.06, 0.06, 0.7, 10]} />
        <meshStandardMaterial color="#4ade80" roughness={0.3} metalness={0.15} transparent opacity={0.7} />
      </mesh>
    </group>
  );
}

/* ---- Orbiting scan rings ---- */
function ScanRings() {
  const ring1 = useRef<THREE.Mesh>(null!);
  const ring2 = useRef<THREE.Mesh>(null!);

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    ring1.current.rotation.x = t * 0.4;
    ring1.current.rotation.y = t * 0.2;
    ring2.current.rotation.x = -t * 0.3;
    ring2.current.rotation.z = t * 0.35;
  });

  return (
    <>
      <mesh ref={ring1}>
        <torusGeometry args={[1.6, 0.018, 12, 80]} />
        <meshStandardMaterial color="#16a34a" transparent opacity={0.4} />
      </mesh>
      <mesh ref={ring2}>
        <torusGeometry args={[2.1, 0.012, 12, 80]} />
        <meshStandardMaterial color="#86efac" transparent opacity={0.25} />
      </mesh>
    </>
  );
}

/* ---- Floating particle dots ---- */
function Particles() {
  const mesh = useRef<THREE.InstancedMesh>(null!);
  const count = 60;

  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      arr[i * 3] = (Math.random() - 0.5) * 8;
      arr[i * 3 + 1] = (Math.random() - 0.5) * 8;
      arr[i * 3 + 2] = (Math.random() - 0.5) * 4;
    }
    return arr;
  }, []);

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    for (let i = 0; i < count; i++) {
      const matrix = new THREE.Matrix4();
      matrix.setPosition(
        positions[i * 3] + Math.sin(t * 0.3 + i) * 0.1,
        positions[i * 3 + 1] + Math.cos(t * 0.2 + i * 0.5) * 0.15,
        positions[i * 3 + 2]
      );
      mesh.current.setMatrixAt(i, matrix);
    }
    mesh.current.instanceMatrix.needsUpdate = true;
  });

  return (
    <instancedMesh ref={mesh} args={[undefined, undefined, count]}>
      <sphereGeometry args={[0.025, 8, 8]} />
      <meshStandardMaterial color="#86efac" transparent opacity={0.6} />
    </instancedMesh>
  );
}

export default function LungScene3D({ className = "" }: { className?: string }) {
  return (
    <div className={`${className}`} style={{ width: "100%", height: "100%" }}>
      <Canvas
        camera={{ position: [0, 0, 4.5], fov: 50 }}
        style={{ background: "transparent" }}
        dpr={[1, 2]}
      >
        <ambientLight intensity={0.6} />
        <directionalLight position={[3, 5, 3]} intensity={1.2} color="#16a34a" />
        <directionalLight position={[-3, -2, -2]} intensity={0.4} color="#86efac" />
        <pointLight position={[0, 0, 3]} intensity={0.8} color="#bbf7d0" />

        <Float speed={2} rotationIntensity={0.3} floatIntensity={0.4}>
          <LungMesh />
        </Float>
        <ScanRings />
        <Particles />
      </Canvas>
    </div>
  );
}


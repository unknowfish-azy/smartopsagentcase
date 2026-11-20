"""宇树官方 MJCF 模型 → GLB + 关节元数据 转换管线。

数据源：https://github.com/unitreerobotics/unitree_mujoco （BSD-3-Clause，
许可文本随模型一并复制到输出目录 UNITREE-LICENSE.txt）。

用法（仓库根目录）：
    python frontend/scripts/import-unitree-model.py <model_dir> <xml_name> <out_name>
    # 例：
    python frontend/scripts/import-unitree-model.py .cache/unitree_mujoco/unitree_robots/go2 go2.xml go2
    python frontend/scripts/import-unitree-model.py .cache/unitree_mujoco/unitree_robots/g1 g1_23dof.xml g1

输出（frontend/public/models/robot/）：
    <out_name>.glb       —— Y-up、米制、home 站立姿态接地（足底 y=0）
    <out_name>.rig.json  —— 关节元数据：{joint: {node, axis, home, range}}，供前端驱动

节点结构（每个可动 body）：
    <body>            相对父 body frame 的固定 pos/quat
      └ <joint_name>  关节 pivot：平移 joint.pos，初始旋转 = home 姿态（前端按名驱动）
          └ <body>__frame  平移 -joint.pos；geom 与子 body 挂在此节点下

坐标系：MJCF Z-up → GLB Y-up，根节点 rotation = R_x(-90°)，
关节在各自 body 局部空间驱动，与全局坐标转换解耦。

依赖：trimesh + numpy（仅用于 OBJ 读取与顶点合并；GLB 写出为本脚本自实现，
避免 trimesh 场景图对空关节节点/节点名的处理不可控）。
沙箱/低内存环境如遇 OpenBLAS 报错，设 OPENBLAS_NUM_THREADS=1 再运行。
"""

from __future__ import annotations

import json
import math
import os
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "frontend" / "public" / "models" / "robot"


# ------------------------------------------------------------------
# 四元数（w,x,y,z）与变换工具
# ------------------------------------------------------------------

def quat_to_mat(q):
    w, x, y, z = q
    n = math.sqrt(w * w + x * x + y * y + z * z) or 1.0
    w, x, y, z = w / n, x / n, y / n, z / n
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])


def axis_angle_to_gltf_quat(axis, angle):
    """MJCF 局部轴角 → glTF 四元数 [x,y,z,w]。"""
    a = np.asarray(axis, dtype=float)
    a = a / (np.linalg.norm(a) or 1.0)
    s = math.sin(angle / 2.0)
    return [float(a[0] * s), float(a[1] * s), float(a[2] * s), float(math.cos(angle / 2.0))]


def mat_to_gltf_quat(m):
    """旋转矩阵 → glTF 四元数 [x,y,z,w]（Shepperd 法）。"""
    tr = m[0, 0] + m[1, 1] + m[2, 2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        w = 0.25 * s
        x = (m[2, 1] - m[1, 2]) / s
        y = (m[0, 2] - m[2, 0]) / s
        z = (m[1, 0] - m[0, 1]) / s
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        w = (m[2, 1] - m[1, 2]) / s
        x = 0.25 * s
        y = (m[0, 1] + m[1, 0]) / s
        z = (m[0, 2] + m[2, 0]) / s
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        w = (m[0, 2] - m[2, 0]) / s
        x = (m[0, 1] + m[1, 0]) / s
        y = 0.25 * s
        z = (m[1, 2] + m[2, 1]) / s
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        w = (m[1, 0] - m[0, 1]) / s
        x = (m[0, 2] + m[2, 0]) / s
        y = (m[1, 2] + m[2, 1]) / s
        z = 0.25 * s
    return [float(x), float(y), float(z), float(w)]


def trs(pos, quat_wxyz):
    m = np.eye(4)
    m[:3, :3] = quat_to_mat(quat_wxyz)
    m[:3, 3] = pos
    return m


def parse_vec(text, default, size=3):
    if not text:
        return list(default)
    vals = [float(v) for v in text.replace(",", " ").split()]
    assert len(vals) == size, f"向量维度不符: {text}"
    return vals


# ------------------------------------------------------------------
# MJCF default class 继承（本模型子集：joint/geom 属性沿 class 链合并）
# ------------------------------------------------------------------

class Defaults:
    def __init__(self, root):
        self.classes = {"__root__": {"parent": None, "attrs": {}}}
        self._walk(root.find("default"), None)

    def _walk(self, elem, parent_name):
        if elem is None:
            return
        name = elem.get("class") or "__root__"
        if name == "__root__" and parent_name is None:
            node = self.classes["__root__"]
        else:
            node = {"parent": parent_name or "__root__", "attrs": {}}
            self.classes[name] = node
        for child in elem:
            if child.tag == "default":
                self._walk(child, name)
            else:
                node["attrs"].setdefault(child.tag, {}).update(child.attrib)

    def resolve(self, tag, class_name, own):
        chain = []
        name = class_name or "__root__"
        while name:
            node = self.classes.get(name)
            if not node:
                break
            chain.append(node)
            name = node["parent"]
        merged = {}
        for node in reversed(chain):
            merged.update(node["attrs"].get(tag, {}))
        merged.update(own)
        return merged


# ------------------------------------------------------------------
# GLB 组装
# ------------------------------------------------------------------

class GlbBuilder:
    def __init__(self):
        self.nodes = []
        self.meshes = []
        self.materials = []
        self.accessors = []
        self.buffer_views = []
        self.bin = bytearray()
        self._mesh_cache = {}
        self._material_cache = {}

    def add_node(self, name, translation=None, rotation=None, mesh=None):
        node = {"name": name, "children": []}
        if translation and any(abs(v) > 1e-12 for v in translation):
            node["translation"] = [float(v) for v in translation]
        if rotation and (abs(rotation[3] - 1) > 1e-12 or any(abs(v) > 1e-12 for v in rotation[:3])):
            node["rotation"] = rotation
        if mesh is not None:
            node["mesh"] = mesh
        self.nodes.append(node)
        return len(self.nodes) - 1

    def link(self, parent, child):
        self.nodes[parent]["children"].append(child)

    def material(self, rgba):
        key = tuple(round(float(v), 5) for v in rgba)
        if key in self._material_cache:
            return self._material_cache[key]
        r, g, b, a = key
        # 亮度越高越接近烤漆/金属外壳；深色件（0.2 档）按橡胶/哑黑处理
        lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
        metallic = 0.55 if lum > 0.55 else 0.25
        roughness = 0.42 if lum > 0.55 else 0.6
        self.materials.append({
            "name": f"m{len(self.materials)}",
            "pbrMetallicRoughness": {
                "baseColorFactor": [r, g, b, a],
                "metallicFactor": metallic,
                "roughnessFactor": roughness,
            },
        })
        idx = len(self.materials) - 1
        self._material_cache[key] = idx
        return idx

    def _accessor(self, array, target, kind):
        data = np.asarray(array, dtype=np.float32 if kind == "VEC3" else None)
        if kind == "SCALAR":
            data = np.asarray(array, dtype=np.uint32)
        blob = data.tobytes()
        offset = len(self.bin)
        self.bin.extend(blob)
        while len(self.bin) % 4:
            self.bin.append(0)
        self.buffer_views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(blob), "target": target})
        acc = {
            "bufferView": len(self.buffer_views) - 1,
            "componentType": 5126 if kind == "VEC3" else 5125,
            "count": int(data.shape[0]),
            "type": kind,
        }
        if kind == "VEC3":
            acc["min"] = [float(v) for v in data.min(axis=0)]
            acc["max"] = [float(v) for v in data.max(axis=0)]
        self.accessors.append(acc)
        return len(self.accessors) - 1

    def mesh(self, key, geometry, rgba):
        if key in self._mesh_cache:
            return self._mesh_cache[key]
        vertices, normals, faces = geometry
        pos = self._accessor(vertices, 34962, "VEC3")
        nor = self._accessor(normals, 34962, "VEC3")
        idx = self._accessor(faces.reshape(-1), 34963, "SCALAR")
        self.meshes.append({
            "name": str(key[0]),
            "primitives": [{
                "attributes": {"POSITION": pos, "NORMAL": nor},
                "indices": idx,
                "material": self.material(rgba),
            }],
        })
        mesh_idx = len(self.meshes) - 1
        self._mesh_cache[key] = mesh_idx
        return mesh_idx

    def export(self, path, root_nodes, extras):
        gltf = {
            "asset": {"version": "2.0", "generator": "SmartOpsAgent import-unitree-model.py"},
            "scene": 0,
            "scenes": [{"nodes": root_nodes}],
            "nodes": self.nodes,
            "meshes": self.meshes,
            "materials": self.materials,
            "accessors": self.accessors,
            "bufferViews": self.buffer_views,
            "buffers": [{"byteLength": len(self.bin)}],
            "extras": extras,
        }
        for node in self.nodes:
            if not node["children"]:
                del node["children"]
        payload = json.dumps(gltf, separators=(",", ":")).encode()
        payload += b" " * ((4 - len(payload) % 4) % 4)
        total = 12 + 8 + len(payload) + 8 + len(self.bin)
        with open(path, "wb") as fh:
            fh.write(struct.pack("<III", 0x46546C67, 2, total))
            fh.write(struct.pack("<II", len(payload), 0x4E4F534A))
            fh.write(payload)
            fh.write(struct.pack("<II", len(self.bin), 0x004E4942))
            fh.write(self.bin)


# ------------------------------------------------------------------
# MJCF 解析与转换
# ------------------------------------------------------------------

def load_geometry(mesh_path):
    loaded = trimesh.load(mesh_path, force="mesh", process=True)
    mesh = loaded
    if not isinstance(mesh, trimesh.Trimesh) or not len(mesh.vertices):
        raise ValueError(f"网格为空: {mesh_path}")
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    normals = np.asarray(mesh.vertex_normals, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    return vertices, normals, faces


def convert(model_dir: Path, xml_name: str, out_name: str, commit: str, home_override=None):
    xml_path = model_dir / xml_name
    tree = ET.parse(xml_path)
    root = tree.getroot()
    compiler = root.find("compiler")
    mesh_dir = model_dir / (compiler.get("meshdir", ".") if compiler is not None else ".")
    if compiler is not None and compiler.get("angle", "degree") == "degree":
        raise ValueError("仅支持 angle=radian 的模型")

    defaults = Defaults(root)

    materials = {}
    asset = root.find("asset")
    mesh_files = {}
    if asset is not None:
        for mat in asset.findall("material"):
            materials[mat.get("name")] = parse_vec(mat.get("rgba"), [0.7, 0.7, 0.7, 1], 4)
        for mesh in asset.findall("mesh"):
            name = mesh.get("name") or Path(mesh.get("file")).stem
            mesh_files[name] = mesh_dir / mesh.get("file")

    # keyframe home：qpos 按 joint 文档序分配（freejoint 占 7 槽）
    home = {}
    key = root.find("keyframe/key")
    if key is not None:
        qpos = [float(v) for v in key.get("qpos").split()]
        cursor = 0
        for body in root.find("worldbody").iter("body"):
            for joint in body.findall("joint"):
                if joint.get("type", "hinge") == "free":
                    cursor += 7
                else:
                    home[joint.get("name")] = qpos[cursor]
                    cursor += 1
            if body.find("freejoint") is not None:
                cursor += 7

    # 展示用站立姿态覆盖：G1 官方零位为「前臂前伸 90°」的 L 形建模姿态，
    # 真机自然站立对应 elbow ≈ +1.4 rad（绕 +Y 把前臂从 +X 放到 -Z），经此覆盖写入 home。
    if home_override:
        for name, value in home_override.items():
            home[name] = float(value)

    glb = GlbBuilder()
    joints_meta = {}
    geom_cache = {}
    fk_jobs = []  # (局部矩阵链累乘用) (node_matrix_world_mjcf, vertices)  home 姿态下求接地

    def geom_rgba(geom, attrs):
        rgba = geom.get("rgba")
        if rgba:
            return parse_vec(rgba, [0.7, 0.7, 0.7, 1], 4)
        mat = attrs.get("material") or geom.get("material")
        if mat and mat in materials:
            return materials[mat]
        return [0.7, 0.7, 0.7, 1]

    def build_body(body, parent_node, parent_fk):
        pos = parse_vec(body.get("pos"), [0, 0, 0])
        quat = parse_vec(body.get("quat"), [1, 0, 0, 0], 4)
        pose_node = glb.add_node(body.get("name"), pos, mat_to_gltf_quat(quat_to_mat(quat)))
        glb.link(parent_node, pose_node)
        fk = parent_fk @ trs(pos, quat)

        hinge = None
        for joint in body.findall("joint"):
            if joint.get("type", "hinge") != "free":
                hinge = joint
                break
        frame_node = pose_node
        frame_fk = fk
        if hinge is not None:
            attrs = defaults.resolve("joint", hinge.get("class"), hinge.attrib)
            axis = parse_vec(attrs.get("axis"), [0, 1, 0])
            jpos = parse_vec(attrs.get("pos"), [0, 0, 0])
            name = hinge.get("name")
            q_home = float(home.get(name, 0.0))
            jrange = parse_vec(attrs.get("range"), [0, 0], 2) if attrs.get("range") else None
            joint_node = glb.add_node(name, jpos, axis_angle_to_gltf_quat(axis, q_home))
            glb.link(pose_node, joint_node)
            joints_meta[name] = {
                "node": name,
                "axis": axis,
                "home": q_home,
                **({"range": jrange} if jrange else {}),
            }
            fk = fk @ trs(jpos, [1, 0, 0, 0]) @ trs([0, 0, 0], quat_from_axis_angle_wxyz(axis, q_home))
            frame_fk = fk @ trs([-v for v in jpos], [1, 0, 0, 0])
            frame_node = glb.add_node(f"{body.get('name')}__frame", [-v for v in jpos])
            glb.link(joint_node, frame_node)

        seen_meshes = set()
        for geom in body.findall("geom"):
            attrs = defaults.resolve("geom", geom.get("class"), geom.attrib)
            mesh_name = geom.get("mesh") or attrs.get("mesh")
            if not mesh_name or mesh_name not in mesh_files:
                continue  # 非 mesh geom（碰撞球/盒等）不导出
            if attrs.get("class") == "collision" or attrs.get("group") == "3":
                continue
            if mesh_name in seen_meshes:
                continue  # G1 同一 mesh 以 group=1 + 无 group 重复声明，去重
            seen_meshes.add(mesh_name)
            rgba = geom_rgba(geom, attrs)
            gpos = parse_vec(geom.get("pos"), [0, 0, 0])
            gquat = parse_vec(geom.get("quat"), [1, 0, 0, 0], 4)
            if mesh_name not in geom_cache:
                geom_cache[mesh_name] = load_geometry(mesh_files[mesh_name])
            geometry = geom_cache[mesh_name]
            mesh_idx = glb.mesh((mesh_name, tuple(rgba)), geometry, rgba)
            gnode = glb.add_node(f"{body.get('name')}::{mesh_name}", gpos, mat_to_gltf_quat(quat_to_mat(gquat)), mesh_idx)
            glb.link(frame_node, gnode)
            fk_jobs.append((frame_fk @ trs(gpos, gquat), geometry[0]))

        for child in body.findall("body"):
            # G1 23dof 尾部 pos="0 0 20" 的占位 body（无 geom 无子级）跳过
            if not child.findall("geom") and not child.findall("body"):
                continue
            build_body(child, frame_node, frame_fk)

    world = root.find("worldbody")
    base = world.find("body")
    if base is None:
        raise ValueError("worldbody 无根 body")
    # 根 body 的 pos 是 freejoint 初始高度，不参与建模；接地由 home 姿态包围盒决定
    base_pos = list(parse_vec(base.get("pos"), [0, 0, 0]))
    base.set("pos", "0 0 0")

    # MJCF Z-up → GLB Y-up：R_x(-90°)
    z_to_y = quat_from_axis_angle_wxyz([1, 0, 0], -math.pi / 2)
    root_node = glb.add_node("unitree_root", rotation=mat_to_gltf_quat(quat_to_mat(z_to_y)))
    build_body(base, root_node, np.eye(4))
    base.set("pos", " ".join(str(v) for v in base_pos))

    # home 姿态接地：所有顶点经 FK（含根旋转）后取 min_y，平移根节点补偿
    min_y = math.inf
    root_rot = trs([0, 0, 0], z_to_y)
    for fk, vertices in fk_jobs:
        world_v = (root_rot @ fk)[:3, :3] @ vertices.T + (root_rot @ fk)[:3, 3:4]
        min_y = min(min_y, float(world_v[1].min()))
    if not math.isfinite(min_y):
        raise ValueError("模型无有效顶点")
    glb.nodes[root_node]["translation"] = [0.0, -min_y, 0.0]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    glb_path = OUT_DIR / f"{out_name}.glb"
    glb.export(glb_path, [root_node], {"source": "unitree_mujoco", "up": "Y", "units": "m"})
    meta = {
        "name": out_name,
        "dof": len(joints_meta),
        "joints": joints_meta,
        "groundOffset": -min_y,
        "source": {
            "repo": "https://github.com/unitreerobotics/unitree_mujoco",
            "path": f"unitree_robots/{model_dir.name}/{xml_name}",
            "commit": commit,
            "license": "BSD-3-Clause",
        },
    }
    (OUT_DIR / f"{out_name}.rig.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"[ok] {glb_path.name}: {glb_path.stat().st_size / 1e6:.2f} MB, "
          f"{len(joints_meta)} joints, ground offset {-min_y:.4f} m")


def quat_from_axis_angle_wxyz(axis, angle):
    a = np.asarray(axis, dtype=float)
    a = a / (np.linalg.norm(a) or 1.0)
    s = math.sin(angle / 2.0)
    return [math.cos(angle / 2.0), float(a[0] * s), float(a[1] * s), float(a[2] * s)]


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(2)
    model_dir = Path(sys.argv[1]).resolve()
    commit = "unknown"
    try:
        import subprocess
        commit = subprocess.run(
            ["git", "-C", str(model_dir), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        pass
    # 可选 home 覆盖：left_elbow_joint=1.4 right_elbow_joint=1.4（避免 shell JSON 引号问题）
    override = dict(item.split("=", 1) for item in sys.argv[4:]) if len(sys.argv) > 4 else None
    convert(model_dir, sys.argv[2], sys.argv[3], commit, override)

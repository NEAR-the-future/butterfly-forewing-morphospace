#--------------------------------------------
#
# Module for wing morphology parameter analysis
#
#--------------------------------------------

import numpy as np
import matplotlib.pyplot as plt


def _curve_length_open(points):
    pts = np.asarray(points, dtype=float).reshape(-1, 2)
    if len(pts) < 2:
        return 0.0
    seg = np.diff(pts, axis=0)
    return float(np.sum(np.hypot(seg[:, 0], seg[:, 1])))


def _extract_two_paths_between_indices(contour, idx_a, idx_b):
    """
    在闭合轮廓上，从 idx_a 到 idx_b 提取两条路径：
    path1: 正向走
    path2: 反向绕回去
    """
    pts = np.asarray(contour, dtype=float).reshape(-1, 2)
    n = len(pts)

    if n < 3:
        return pts, pts

    if idx_a <= idx_b:
        path1 = pts[idx_a:idx_b + 1]
        path2 = np.vstack([pts[idx_b:], pts[:idx_a + 1]])
    else:
        path1 = np.vstack([pts[idx_a:], pts[:idx_b + 1]])
        path2 = pts[idx_b:idx_a + 1]

    return path1, path2


def _window_turning_angle(window_pts, debug=False):
    """
    计算一个滑动窗口的“折角”（单位：度）

    debug=True 时，会打印：
    - 当前窗口点
    - v1 / v2 向量
    - 向量长度
    - cosθ
    - 最终角度
    """

    pts = np.asarray(window_pts, dtype=float).reshape(-1, 2)

    if len(pts) < 3:
        if debug:
            print("[angle] Not enough points")
        return np.nan

    # -------------------------------------------------
    # 1) 去除重复点（避免数值问题）
    # -------------------------------------------------
    cleaned = [pts[0]]
    for i in range(1, len(pts)):
        if np.linalg.norm(pts[i] - cleaned[-1]) > 1e-12:
            cleaned.append(pts[i])
    pts = np.asarray(cleaned, dtype=float)

    n = len(pts)
    if n < 3:
        if debug:
            print("[angle] Too few points after cleaning")
        return np.nan

    # -------------------------------------------------
    # 2) 取前半段和后半段方向
    # -------------------------------------------------
    mid = n // 2

    v1 = pts[mid] - pts[0]     # 前半段方向
    v2 = pts[-1] - pts[mid]    # 后半段方向

    n1 = np.linalg.norm(v1)
    n2 = np.linalg.norm(v2)

    if n1 < 1e-12 or n2 < 1e-12:
        if debug:
            print("[angle] Zero-length vector detected")
        return np.nan

    # -------------------------------------------------
    # 3) 计算夹角
    # -------------------------------------------------
    cos_theta = np.dot(v1, v2) / (n1 * n2)
    cos_theta = np.clip(cos_theta, -1.0, 1.0)

    theta_deg = np.degrees(np.arccos(cos_theta))

    # -------------------------------------------------
    # 4) Debug 输出
    # -------------------------------------------------
    if debug:
        print("\n[window turning angle debug]")
        # print(f"points:\n{pts}")
        # print(f"mid index: {mid}")
        # print(f"v1 (start->mid): {v1}, |v1|={n1}")
        # print(f"v2 (mid->end):   {v2}, |v2|={n2}")
        # print(f"cos(theta): {cos_theta}")
        print(f"angle (deg): {theta_deg}")

    return float(theta_deg)


def _detect_tip_compensation_point(path_points, threshold=45.0, window_size=9, search_ratio=0.25, debug=False):
    """
    在 tip -> root 的有序前缘路径上做滑窗折角检测：
      123456789, 2345678910, ...

    只在 tip->root 的前 search_ratio 段内搜索，默认只搜索前 1/4，
    这样更快，也能减少 root 附近噪点干扰。

    当第一次出现 turning_angle > threshold 时，
    返回该窗口中心点作为新的翼尖候选点。
    """
    pts = np.asarray(path_points, dtype=float).reshape(-1, 2)

    if len(pts) < window_size:
        return None

    # 只取 tip->root 的前 1/4 段参与搜索
    search_count = max(window_size, int(np.ceil(len(pts) * search_ratio)))
    search_count = min(search_count, len(pts))
    pts_search = pts[:search_count]

    if len(pts_search) < window_size:
        return None

    half = window_size // 2

    for start in range(0, len(pts_search) - window_size + 1):
        window = pts_search[start:start + window_size]
        angle_deg = _window_turning_angle(window, debug=True)

        if debug:
            print(f"window {start}:{start+window_size}, angle={angle_deg}")

        if np.isfinite(angle_deg) and angle_deg > threshold:
            center_idx = start + half
            return tuple(pts_search[center_idx])

    return None


def tip_locate(edge_points, red_dot, bending_threshold=45.0, window_size=9, poly_deg=3, n_samples=100):
    """
    翼尖检测逻辑：
    1. 先取距离翼根最远的点作为原始翼尖
    2. 根据 root / tip 将闭合轮廓拆成两条路径，短路径视为前缘 LE，长路径视为后缘 TE
    3. 保证 LE 方向为 root -> tip
    4. 将 LE 反转为 tip -> root
    5. 只取 tip->root 的前 1/4 段做滑窗折角检测
    6. 当第一次窗口折角 > bending_threshold(单位：度) 时，
       将该窗口中心点设为新的翼尖
    7. 若始终未超过阈值，则保持原始最远点不变

    注意：
    - bending_threshold 现在虽然保留原名字，但实际表示“折角阈值（度）”
    - poly_deg / n_samples 仅为兼容旧调用而保留，这里不再使用
    """
    if edge_points is None or red_dot is None:
        return None
    if len(edge_points) == 0:
        return None

    pts = np.asarray(edge_points, dtype=float).reshape(-1, 2)
    root = np.asarray(red_dot, dtype=float).reshape(2,)

    # 1) 原始翼尖：距翼根最远的点
    distances = np.linalg.norm(pts - root, axis=1)
    tip_index = int(np.argmax(distances))
    wing_tip = tuple(pts[tip_index])

    # 2) 找 root 在轮廓上的最近点索引
    root_index = int(np.argmin(np.linalg.norm(pts - root, axis=1)))
    if root_index == tip_index:
        return wing_tip

    # 3) 从 root 到 tip 拆出两条路径，短 = LE
    path1, path2 = _extract_two_paths_between_indices(pts, root_index, tip_index)
    len1 = _curve_length_open(path1)
    len2 = _curve_length_open(path2)

    if len1 <= len2:
        le_points = path1
    else:
        le_points = path2

    # 4) 保证 LE 方向为 root -> tip
    if np.linalg.norm(le_points[0] - root) > np.linalg.norm(le_points[-1] - root):
        le_points = le_points[::-1]

    # 5) 反转成 tip -> root
    le_tip_to_root = le_points[::-1]

    # 6) 只在前 1/4 段做折角检测
    le_candidate = _detect_tip_compensation_point(
        le_tip_to_root,
        threshold=bending_threshold,
        window_size=window_size,
        search_ratio=0.25,
        debug=False
    )

    # 7) 有候选点则替换，否则保持原始翼尖
    if le_candidate is not None:
        return tuple(le_candidate)

    return wing_tip


#--------------------------------------------

def get_perimeter(le_points, te_points):
    """
    Compute lengths of LE and TE
    
    Input
    ----------
    le_points       List of (x,y) leading edge points (root to tip, including both)
    te_points       List of (x,y) trailing edge points (root to tip, including both)
    
    Output
    ----------
    LE_length       Length of leading edge
    TE_length       Length of trailing edge
    """
    # LE
    LE_length = 0.0
    for i in range(len(le_points) - 1):
        x1, y1 = le_points[i]
        x2, y2 = le_points[i + 1]
        LE_length += np.sqrt((x2 - x1)**2 + (y2 - y1)**2)

    # TE
    TE_length = 0.0
    for i in range(len(te_points) - 1):
        x1, y1 = te_points[i]
        x2, y2 = te_points[i + 1]
        TE_length += np.sqrt((x2 - x1)**2 + (y2 - y1)**2)  
    
    return LE_length, TE_length


#--------------------------------------------

def get_moments(le_points, te_points, wing_root, wing_tip, moment=1, axis="spanwise"):
    """
    Compute n-th moment of area about specified axis.
    
    Input
    ----------
    le_points       List of (x,y) leading edge points
    te_points       List of (x,y) trailing edge points
    wing_root       (x,y) coordinates of wing root
    wing_tip        (x,y) coordinates of wing tip
    moment          Order of moment (0=area, 1=first, 2=second, 3=third)
    axis            Moment about spanwise (x) or "chordwise (y) axis
    
    Output
    ----------
    float           n-th moment of area of the wing
    """
    n_sections = len(le_points) - 1
    total_moment = 0.0
    
    # Compute spanwise and chordwise unit vectors
    span_vector = np.array(wing_tip) - np.array(wing_root)
    span_length = np.linalg.norm(span_vector)
    
    if span_length > 0:
        span_dir = span_vector / span_length
        chord_dir = np.array([-span_dir[1], span_dir[0]])
    else:
        # Degenerate case: no span, use default axes
        span_dir = np.array([1, 0])
        chord_dir = np.array([0, 1])
    
    # Determine which axis to measure distance along
    if axis.lower() == "chordwise":
        # Moment about chordwise axis = distance along spanwise direction
        axis_dir = span_dir
    elif axis.lower() == "spanwise":
        # Moment about spanwise axis = distance along chordwise direction
        axis_dir = chord_dir
    else:
        raise ValueError("axis must be 'spanwise' or 'chordwise'")
    
    # Convert wing_root to vector for distance calculations
    root_vec = np.array(wing_root)
    

    for i in range(n_sections):
        # Form section vertices (ordered counterclockwise)
        vertices_list = []
        
        # Add leading edge points
        vertices_list.append(le_points[i])
        vertices_list.append(le_points[i + 1])
        
        # Add trailing edge points (reverse order to maintain CCW orientation)
        vertices_list.append(te_points[i + 1])
        vertices_list.append(te_points[i])
        
        # Remove duplicates (for triangular root/tip sections)
        unique_vertices = []
        for v in vertices_list:
            if not any(np.array_equal(v, uv) for uv in unique_vertices):
                unique_vertices.append(v)
        
        # Ensure we have at least 3 points
        if len(unique_vertices) < 3:
            continue
        
        vertices = np.array(unique_vertices)
        
        # Calculate section area
        x, y = vertices[:, 0], vertices[:, 1]
        area = 0.5 * np.abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))
        
        if moment == 0:
            total_moment += area
            continue
        
        # Calculate centroid
        centroid = get_section_centroid(vertices)

        # Calculate signed distance from axis through wing root
        # Axis passes through wing root, perpendicular to axis_dir
        centroid_vec = np.array(centroid)

        distance = np.dot(centroid_vec - root_vec, axis_dir)

        # Calculate n-th moment contribution
        if moment == 1:
            total_moment += area * distance
        elif moment == 2:
            total_moment += area * (distance ** 2)
        elif moment == 3:
            total_moment += area * (distance ** 3)
        else:
            raise ValueError("moment must be 0, 1, 2, or 3")

    
    return total_moment


#--------------------------------------------

def get_sectional_area(le_points, te_points):
    """
    Calculate area of each wing section (handles triangles and quadrilaterals).
    
    Input
    ----------
    le_points       List of (x,y) leading edge points (root to tip, including both)
    te_points       List of (x,y) trailing edge points (root to tip, including both)
    
    Output
    ----------
    numpy array     Area of each wing section
    """
    n_sections = len(le_points) - 1
    sectional_areas = np.zeros(n_sections)
    
    for i in range(n_sections):
        # Extract points for this section
        p1 = le_points[i]      # LE at section start
        p2 = le_points[i + 1]  # LE at section end
        p3 = te_points[i + 1]  # TE at section end
        p4 = te_points[i]      # TE at section start
        
        # Check for triangle vs quadrilateral
        is_root_section = (i == 0 and np.array_equal(p1, p4))
        is_tip_section = (i == n_sections - 1 and np.array_equal(p2, p3))
        
        if is_root_section:
            # Root section: triangle (p1/p4, p2, p3)
            vertices = np.array([p1, p2, p3])
        elif is_tip_section:
            # Tip section: triangle (p1, p2/p3, p4)
            vertices = np.array([p1, p2, p4])
        else:
            # Middle section: quadrilateral (p1, p2, p3, p4)
            vertices = np.array([p1, p2, p3, p4])
        
        # Shoelace formula (works for any polygon)
        x = vertices[:, 0]
        y = vertices[:, 1]
        area = 0.5 * np.abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))
        sectional_areas[i] = area
    
    return sectional_areas


#--------------------------------------------

def get_section_centroid(vertices):
    """
    Compute centroid of a polygon section using proper signed formula.
    """
    if len(vertices) < 3:
        return np.mean(vertices, axis=0) if len(vertices) > 0 else (0, 0)
    
    # Convert to numpy arrays
    x = vertices[:, 0]
    y = vertices[:, 1]
    n = len(vertices)
    
    # Compute signed area using shoelace formula
    signed_area = 0.0
    cx = 0.0
    cy = 0.0
    
    for i in range(n):
        j = (i + 1) % n
        cross_product = x[i] * y[j] - x[j] * y[i]
        signed_area += cross_product
        
        # Accumulate centroid components
        cx += (x[i] + x[j]) * cross_product
        cy += (y[i] + y[j]) * cross_product
    
    signed_area *= 0.5
    
    # Avoid division by zero
    if abs(signed_area) < 1e-10:
        return np.mean(vertices, axis=0)
    
    # Final centroid calculation
    cx = cx / (6 * signed_area)
    cy = cy / (6 * signed_area)
    
    return cx, cy

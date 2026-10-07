
import numpy as np
import matplotlib.pyplot as plt


def _curve_length_open(points):
    pts = np.asarray(points, dtype=float).reshape(-1, 2)
    if len(pts) < 2:
        return 0.0
    seg = np.diff(pts, axis=0)
    return float(np.sum(np.hypot(seg[:, 0], seg[:, 1])))


def _extract_two_paths_between_indices(contour, idx_a, idx_b):

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

    pts = np.asarray(window_pts, dtype=float).reshape(-1, 2)

    if len(pts) < 3:
        if debug:
            print("[angle] Not enough points")
        return np.nan

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


    mid = n // 2

    v1 = pts[mid] - pts[0]     
    v2 = pts[-1] - pts[mid]    

    n1 = np.linalg.norm(v1)
    n2 = np.linalg.norm(v2)

    if n1 < 1e-12 or n2 < 1e-12:
        if debug:
            print("[angle] Zero-length vector detected")
        return np.nan


    cos_theta = np.dot(v1, v2) / (n1 * n2)
    cos_theta = np.clip(cos_theta, -1.0, 1.0)

    theta_deg = np.degrees(np.arccos(cos_theta))


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

    pts = np.asarray(path_points, dtype=float).reshape(-1, 2)

    if len(pts) < window_size:
        return None

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

    if edge_points is None or red_dot is None:
        return None
    if len(edge_points) == 0:
        return None

    pts = np.asarray(edge_points, dtype=float).reshape(-1, 2)
    root = np.asarray(red_dot, dtype=float).reshape(2,)

    distances = np.linalg.norm(pts - root, axis=1)
    tip_index = int(np.argmax(distances))
    wing_tip = tuple(pts[tip_index])


    root_index = int(np.argmin(np.linalg.norm(pts - root, axis=1)))
    if root_index == tip_index:
        return wing_tip


    path1, path2 = _extract_two_paths_between_indices(pts, root_index, tip_index)
    len1 = _curve_length_open(path1)
    len2 = _curve_length_open(path2)

    if len1 <= len2:
        le_points = path1
    else:
        le_points = path2


    if np.linalg.norm(le_points[0] - root) > np.linalg.norm(le_points[-1] - root):
        le_points = le_points[::-1]


    le_tip_to_root = le_points[::-1]

   
    le_candidate = _detect_tip_compensation_point(
        le_tip_to_root,
        threshold=bending_threshold,
        window_size=window_size,
        search_ratio=0.25,
        debug=False
    )

    if le_candidate is not None:
        return tuple(le_candidate)

    return wing_tip


def get_perimeter(le_points, te_points):

 
    LE_length = 0.0
    for i in range(len(le_points) - 1):
        x1, y1 = le_points[i]
        x2, y2 = le_points[i + 1]
        LE_length += np.sqrt((x2 - x1)**2 + (y2 - y1)**2)

  
    TE_length = 0.0
    for i in range(len(te_points) - 1):
        x1, y1 = te_points[i]
        x2, y2 = te_points[i + 1]
        TE_length += np.sqrt((x2 - x1)**2 + (y2 - y1)**2)  
    
    return LE_length, TE_length


def get_moments(le_points, te_points, wing_root, wing_tip, moment=1, axis="spanwise"):

    n_sections = len(le_points) - 1
    total_moment = 0.0
    
    span_vector = np.array(wing_tip) - np.array(wing_root)
    span_length = np.linalg.norm(span_vector)
    
    if span_length > 0:
        span_dir = span_vector / span_length
        chord_dir = np.array([-span_dir[1], span_dir[0]])
    else:
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
    
    root_vec = np.array(wing_root)
    

    for i in range(n_sections):
        vertices_list = []

        vertices_list.append(le_points[i])
        vertices_list.append(le_points[i + 1])
        
        vertices_list.append(te_points[i + 1])
        vertices_list.append(te_points[i])
        
        unique_vertices = []
        for v in vertices_list:
            if not any(np.array_equal(v, uv) for uv in unique_vertices):
                unique_vertices.append(v)

        if len(unique_vertices) < 3:
            continue
        
        vertices = np.array(unique_vertices)

        x, y = vertices[:, 0], vertices[:, 1]
        area = 0.5 * np.abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))
        
        if moment == 0:
            total_moment += area
            continue

        centroid = get_section_centroid(vertices)

        centroid_vec = np.array(centroid)

        distance = np.dot(centroid_vec - root_vec, axis_dir)

        if moment == 1:
            total_moment += area * distance
        elif moment == 2:
            total_moment += area * (distance ** 2)
        elif moment == 3:
            total_moment += area * (distance ** 3)
        else:
            raise ValueError("moment must be 0, 1, 2, or 3")

    
    return total_moment


def get_sectional_area(le_points, te_points):

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
            vertices = np.array([p1, p2, p3])
        elif is_tip_section:
            vertices = np.array([p1, p2, p4])
        else:
            vertices = np.array([p1, p2, p3, p4])
        
        x = vertices[:, 0]
        y = vertices[:, 1]
        area = 0.5 * np.abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))
        sectional_areas[i] = area
    
    return sectional_areas


def get_section_centroid(vertices):
    if len(vertices) < 3:
        return np.mean(vertices, axis=0) if len(vertices) > 0 else (0, 0)
    
    # Convert to numpy arrays
    x = vertices[:, 0]
    y = vertices[:, 1]
    n = len(vertices)
    
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

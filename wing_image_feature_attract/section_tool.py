#--------------------------------------------
#
# Module for wing section division
#
#--------------------------------------------

import numpy as np
import matplotlib.pyplot as plt


def wing_section(edge_points, wing_root, wing_tip, num_sections=10):
    """
    Divide wing into evenly spaced sections perpendicular to the span line.
    
    Input
    ----------
    edge_points     Sorted list of (x,y) edge coordinates
    wing_root         (x,y) coordinates of wing root
    wing_tip        (x,y) coordinates of wing tip
    num_sections    Number of sections to divide the wing into
    
    Output
    ----------
    tuple: (leading_edge_points, trailing_edge_points, wing_root, wing_tip)
           Each edge_points array contains section intersection points
    """
    # 1. Divide edge_points into leading and trailing edges
    leading_edge, trailing_edge = split_edges_by_span(edge_points, wing_root, wing_tip)
    def max_jump(points):
        d = []
        for i in range(len(points)-1):
            d.append(np.linalg.norm(np.array(points[i+1]) - np.array(points[i])))
        return np.max(d), np.median(d)

    print("LE jump:", max_jump(leading_edge))
    print("TE jump:", max_jump(trailing_edge))

    if not leading_edge or not trailing_edge:
        print("Warning: Could not properly split edges")
        return None, None
    
    # 2. Generate evenly spaced points along span line
    span_points = interpolate_span_line(wing_root, wing_tip, num_sections)
    # ✅ add this line to validate split output
    #debug_split_edges(edge_points, leading_edge, trailing_edge, wing_root, wing_tip, show_plot=True)
    #check_edge(edge_points, leading_edge, trailing_edge, wing_root, wing_tip)

    span_vector = np.array([wing_tip[0] - wing_root[0], wing_tip[1] - wing_root[1]])
    span_length = np.linalg.norm(span_vector)   
    span_dir = span_vector / span_length
    perp_dir = np.array([-span_dir[1], span_dir[0]])  # 90 degree rotation
    
    # 4. Find intersection points for each section
    leading_edge_sections = []
    trailing_edge_sections = []

    for i, span_pt in enumerate(span_points):
        # For the first and last points, use exact root/tip
        if i == 0:
            leading_edge_sections.append(wing_root)
            trailing_edge_sections.append(wing_root)
            continue
        elif i == len(span_points) - 1:
            leading_edge_sections.append(wing_tip)
            trailing_edge_sections.append(wing_tip)
            continue

        # Create chord line perpendicular to span at this point
        le_intersection = find_chord_intersection(span_pt, span_dir, perp_dir, leading_edge, wing_root)
        te_intersection = find_chord_intersection(span_pt, span_dir, perp_dir, trailing_edge, wing_root)


        if le_intersection and te_intersection:
            leading_edge_sections.append(le_intersection)
            trailing_edge_sections.append(te_intersection)
        else:
            # Fallback: use nearest point on edge
            print(f"Warning: Could not find exact intersection for section {i}")
            if le_intersection is None:
                le_intersection = find_nearest_point_on_edge(span_pt, leading_edge)
            if te_intersection is None:
                te_intersection = find_nearest_point_on_edge(span_pt, trailing_edge)
            
            leading_edge_sections.append(le_intersection)
            trailing_edge_sections.append(te_intersection)

    return leading_edge_sections, trailing_edge_sections


#--------------------------------------------
def check_edge(edge_points, leading_edge, trailing_edge, wing_root, wing_tip):
    """
    Visual check of edge split in IMAGE (pixel) coordinate system:
    - Origin at top-left
    - y axis points downward
    """

    import matplotlib.pyplot as plt
    import numpy as np

    edge = np.array(edge_points)
    le = np.array(leading_edge)
    te = np.array(trailing_edge)

    fig, ax = plt.subplots(figsize=(6, 6))

    # ---- plot edges ----
    ax.plot(edge[:, 0], edge[:, 1],
            'r.', markersize=2, label='Extracted edge')

    ax.plot(le[:, 0], le[:, 1],
            'b.', markersize=4, label='Leading edge')

    ax.plot(te[:, 0], te[:, 1],
            'c.', markersize=4, label='Trailing edge')

    # ---- plot span line ----
    ax.plot([wing_root[0], wing_tip[0]],
            [wing_root[1], wing_tip[1]],
            'k-', linewidth=2, label='Span line')

    # ---- mark root & tip ----
    ax.plot(wing_root[0], wing_root[1], 'kx', markersize=10)
    ax.plot(wing_tip[0], wing_tip[1], 'kx', markersize=10)

    # ---- IMPORTANT: image coordinate system ----
    ax.set_aspect('equal', adjustable='box')
    ax.invert_yaxis()          # 🔑 核心：y 轴向下
    ax.set_xlabel('x (pixel)')
    ax.set_ylabel('y (pixel)')
    ax.set_title('Edge split check (image coordinate system)')

    ax.legend()
    ax.grid(False)

    plt.tight_layout()
    plt.show()
        
def debug_split_edges(edge_points, leading_edge, trailing_edge, wing_root, wing_tip, show_plot=True):
    """
    Debug helper to validate split_edges_by_span output.
    Prints indices/lengths/endpoint checks and optionally plots.
    """
    if not edge_points or not leading_edge or not trailing_edge:
        print("[debug_split_edges] Empty input or split failed.")
        return

    wing_root = np.array(wing_root, dtype=float)
    wing_tip = np.array(wing_tip, dtype=float)

    # --- helper: polyline length ---
    def polyline_length(points):
        if len(points) < 2:
            return 0.0
        length = 0.0
        for i in range(len(points) - 1):
            p1 = np.array(points[i], dtype=float)
            p2 = np.array(points[i + 1], dtype=float)
            length += np.linalg.norm(p2 - p1)
        return float(length)

    def dist(a, b):
        a = np.array(a, dtype=float)
        b = np.array(b, dtype=float)
        return float(np.linalg.norm(a - b))

    root_idx = find_nearest_index(edge_points, tuple(wing_root))
    tip_idx  = find_nearest_index(edge_points, tuple(wing_tip))

    le_len = polyline_length(leading_edge)
    te_len = polyline_length(trailing_edge)

    le_start_d = dist(leading_edge[0], wing_root)
    le_end_d   = dist(leading_edge[-1], wing_tip)
    te_start_d = dist(trailing_edge[0], wing_root)
    te_end_d   = dist(trailing_edge[-1], wing_tip)

    print("\n========== split_edges_by_span DEBUG ==========")
    print(f"Total edge points: {len(edge_points)}")
    print(f"Nearest index to root: {root_idx}, nearest index to tip: {tip_idx}")
    print(f"Leading edge:  points={len(leading_edge)},  length={le_len:.6f}")
    print(f"Trailing edge: points={len(trailing_edge)}, length={te_len:.6f}")
    print("--- Endpoint distance checks (should be small) ---")
    print(f"LE start -> root: {le_start_d:.6e}, LE end -> tip: {le_end_d:.6e}")
    print(f"TE start -> root: {te_start_d:.6e}, TE end -> tip: {te_end_d:.6e}")

    # quick sanity: which one is shorter (your split rule)
    shorter = "leading_edge" if le_len <= te_len else "trailing_edge"
    print(f"Shorter polyline according to lengths: {shorter}")

    # optional: visualize
    if show_plot:
        # reuse your existing plot util: it expects points lists for le/te
        check_edge(edge_points, leading_edge, trailing_edge, tuple(wing_root), tuple(wing_tip))
    print("==============================================\n")

#--------------------------------------------
def find_chord_intersection(span_point, span_dir, perp_dir, edge_points, wing_root):
    """
    Robust intersection between a chord line (perpendicular to span) and an edge polyline.

    We work in (u, v) coordinates:
      u = dot(p - root, span_dir)  (spanwise)
      v = dot(p - root, perp_dir)  (chordwise)
    A chord section at span_point corresponds to u = u0.

    Steps:
      1) Compute u0 for the section.
      2) Find all polyline segments whose endpoints straddle u0.
      3) Interpolate intersection point on those segments by u.
      4) Keep candidates on the dominant side of the edge (sign of median v).
      5) Choose the candidate closest to span_point along chord (min |v - v_span|).
    """
    if len(edge_points) < 2:
        return None

    root = np.array(wing_root, dtype=float)
    span_point = np.array(span_point, dtype=float)
    span_dir = np.array(span_dir, dtype=float)
    perp_dir = np.array(perp_dir, dtype=float)

    # spanwise coordinate of this section
    u0 = float(np.dot(span_point - root, span_dir))
    v_span = float(np.dot(span_point - root, perp_dir))  # should be ~0 if span_point lies on span line

    # determine dominant side of this edge in chordwise direction (v)
    step = max(1, len(edge_points) // 200)
    v_samples = []
    for p in edge_points[::step]:
        p = np.array(p, dtype=float)
        v_samples.append(float(np.dot(p - root, perp_dir)))
    if v_samples:
        v_med = float(np.median(v_samples))
        expected_sign = 1 if v_med > 0 else (-1 if v_med < 0 else 0)
    else:
        expected_sign = 0

    candidates = []  # (dist_along_chord, v, (x,y))
    for i in range(len(edge_points) - 1):
        p1 = np.array(edge_points[i], dtype=float)
        p2 = np.array(edge_points[i + 1], dtype=float)

        u1 = float(np.dot(p1 - root, span_dir))
        u2 = float(np.dot(p2 - root, span_dir))

        d1 = u1 - u0
        d2 = u2 - u0

        # segment crosses u0 (or touches)
        if d1 == 0.0 and d2 == 0.0:
            # segment lies on the same u slice; take closer endpoint to span_point
            v1 = float(np.dot(p1 - root, perp_dir))
            v2 = float(np.dot(p2 - root, perp_dir))
            c1 = (abs(v1 - v_span), v1, (float(p1[0]), float(p1[1])))
            c2 = (abs(v2 - v_span), v2, (float(p2[0]), float(p2[1])))
            candidates.extend([c1, c2])
            continue

        if d1 * d2 <= 0.0 and (u2 != u1):
            # linear interpolation by u
            t = (u0 - u1) / (u2 - u1)
            if 0.0 <= t <= 1.0:
                inter = p1 + t * (p2 - p1)
                v = float(np.dot(inter - root, perp_dir))
                candidates.append((abs(v - v_span), v, (float(inter[0]), float(inter[1]))))

    if not candidates:
        return None

    # prefer candidates on the dominant side of this edge
    if expected_sign != 0:
        filtered = []
        for distc, v, pt in candidates:
            sgn = 1 if v > 0 else (-1 if v < 0 else 0)
            if sgn == expected_sign or sgn == 0:
                filtered.append((distc, v, pt))
        if filtered:
            candidates = filtered

    # choose closest along chord direction
    candidates.sort(key=lambda x: x[0])
    return candidates[0][2]




#--------------------------------------------

def split_edges_by_span(edge_points, wing_root, wing_tip):
    """
    Split continuous edge into leading and trailing edges
    using total polyline length instead of point count.
    """
    if len(edge_points) < 3:
        return [], []

    # --- helper: compute polyline length ---
    def polyline_length(points):
        if len(points) < 2:
            return 0.0
        length = 0.0
        for i in range(len(points) - 1):
            p1 = np.array(points[i])
            p2 = np.array(points[i + 1])
            length += np.linalg.norm(p2 - p1)
        return length

    # Find nearest indices to root and tip
    root_idx = find_nearest_index(edge_points, wing_root)
    tip_idx = find_nearest_index(edge_points, wing_tip)

    # Ensure ordering
    if root_idx > tip_idx:
        root_idx, tip_idx = tip_idx, root_idx

    # Two possible paths along the closed contour
    segment1 = edge_points[root_idx:tip_idx + 1]
    segment2 = edge_points[tip_idx:] + edge_points[:root_idx + 1]

    # Reverse segment2 so both go root → tip
    segment2 = segment2[::-1]

    # --- NEW: length-based comparison ---
    len1 = polyline_length(segment1)
    len2 = polyline_length(segment2)

    # Shorter = leading edge, longer = trailing edge
    if len1 <= len2:
        leading_edge = segment1
        trailing_edge = segment2
    else:
        leading_edge = segment2
        trailing_edge = segment1

    return leading_edge, trailing_edge

#--------------------------------------------

def interpolate_span_line(wing_root, wing_tip, num_points):
    """
    Generate evenly spaced points along the span line.
    """
    points = []
    
    for i in range(num_points + 1):
        t = i / num_points
        x = wing_root[0] + t * (wing_tip[0] - wing_root[0])
        y = wing_root[1] + t * (wing_tip[1] - wing_root[1])
        points.append((x, y))
    
    return points


#--------------------------------------------

def find_nearest_point_on_edge(point, edge_points):
    """
    Find nearest point on edge to given point.
    """
    if not edge_points:
        return None
    
    distances = [((p[0] - point[0])**2 + (p[1] - point[1])**2) for p in edge_points]
    nearest_idx = np.argmin(distances)
    return edge_points[nearest_idx]


#--------------------------------------------

def find_nearest_index(points, target_point):
    """
    Find index of point in list nearest to target_point.
    """
    distances = [((p[0] - target_point[0])**2 + (p[1] - target_point[1])**2) for p in points]
    return np.argmin(distances)


#--------------------------------------------

def sort_points_along_curve(points, start_point, end_point):
    """
    Sort points to form continuous curve from start to end.
    """
    if len(points) <= 2:
        return points
    
    # Find start and end indices
    start_idx = find_nearest_index(points, start_point)
    end_idx = find_nearest_index(points, end_point)
    
    # Reorder points from start to end
    if start_idx <= end_idx:
        sorted_points = points[start_idx:end_idx + 1]
    else:
        sorted_points = points[start_idx:] + points[:end_idx + 1]
    
    return sorted_points


#--------------------------------------------

def wing_rotate_scale(le_points, te_points, wing_root, wing_tip):
    """
    Rotate and scale wing so span aligns with x-axis (span=1) and chord with y-axis,
    then shift to first quadrant.
    
    Input
    ----------
    le_points       List of (x,y) leading edge points
    te_points       List of (x,y) trailing edge points
    wing_root       (x,y) coordinates of wing root
    wing_tip        (x,y) coordinates of wing tip
    
    Output
    ----------
    tuple: (le_points_transformed, te_points_transformed, wing_root_transformed, wing_tip_transformed)
    """
    # Convert to numpy arrays
    le_array = np.array(le_points)
    te_array = np.array(te_points)
    root = np.array(wing_root)
    tip = np.array(wing_tip)
    
    # 1. Translate so root is at origin
    le_translated = le_array - root
    te_translated = te_array - root
    tip_translated = tip - root
    
    # 2. Compute rotation angle to align span with positive x-axis
    span_vector = tip_translated
    span_length = np.linalg.norm(span_vector)
    
    # Compute rotation angle (-angle to align span with +x)
    angle = -np.arctan2(span_vector[1], span_vector[0])
    
    # 3. Create rotation matrix
    cos_a, sin_a = np.cos(angle), np.sin(angle)
    R = np.array([[cos_a, -sin_a], [sin_a, cos_a]])
    
    # 4. Rotate all points
    le_rotated = np.dot(le_translated, R.T)
    te_rotated = np.dot(te_translated, R.T)
    tip_rotated = np.dot(tip_translated, R.T)
    
    # 5. Scale so span becomes 1
    le_scaled = le_rotated / span_length
    te_scaled = te_rotated / span_length
    tip_scaled = tip_rotated / span_length
    root_scaled = np.array([0.0, 0.0])  # Root stays at origin
    
    # 6. Ensure x increases from root to tip (tip should have x=1)
    # If tip's x is negative, rotate 180 degrees around origin
    if tip_scaled[0] < 0:
        le_scaled = -le_scaled  # Rotate 180� = multiply by -1
        te_scaled = -te_scaled
        root_scaled = -root_scaled
        tip_scaled = -tip_scaled
      
    # 7. Ensure wing is in first quadrant (x, y >= 0)
    # Find minimum coordinates of all points
    all_points = np.vstack([le_scaled, te_scaled, [root_scaled], [tip_scaled]])
    min_x, min_y = np.min(all_points, axis=0)
    
    # Shift to first quadrant if needed
    if min_x < 0 or min_y < 0:
        le_scaled = le_scaled - [min_x, min_y]
        te_scaled = te_scaled - [min_x, min_y]
        root_scaled = root_scaled - [min_x, min_y]
        tip_scaled = tip_scaled - [min_x, min_y]

    # Convert back to tuples
    le_transformed = [tuple(p) for p in le_scaled]
    te_transformed = [tuple(p) for p in te_scaled]
    root_transformed = tuple(root_scaled)
    tip_transformed = tuple(tip_scaled)
    
    # Verify final orientation
    final_tip = np.array(tip_transformed)
    final_root = np.array(root_transformed)
    
    # Ensure root to tip has positive x difference
    if final_tip[0] <= final_root[0]:
        print("Warning: Span not aligned with positive x-axis after transformation")

    return le_transformed, te_transformed, root_transformed, tip_transformed

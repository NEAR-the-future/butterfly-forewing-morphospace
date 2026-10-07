import cv2
import numpy as np
import os
from pathlib import Path


def import_image(image_path):
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"Failed to load image: {image_path}")

    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return img


def convert_to_grayscale(image, save_path=None):
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    if save_path:
        save_path = str(Path(save_path).with_suffix('.png'))
        cv2.imwrite(save_path, gray)
    return gray


def detect_red_dot(image, min_dot_size=20):
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)

    lower_red1 = np.array([0, 100, 100])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([160, 100, 100])
    upper_red2 = np.array([180, 255, 255])

    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
    red_mask = cv2.bitwise_or(mask1, mask2)

    kernel = np.ones((3, 3), np.uint8)
    red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, kernel)
    red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    valid = [c for c in contours if cv2.contourArea(c) >= min_dot_size]
    if not valid:
        return None

    c = max(valid, key=cv2.contourArea)
    M = cv2.moments(c)
    if M["m00"] == 0:
        return None

    return (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))




def detect_blue_circle(image, min_area=20):
    """
    检测原图中的蓝色圆圈，并返回其中心点 (x, y)。
    若未检测到则返回 None。

    逻辑：
    1. 在 HSV 空间阈值提取蓝色
    2. 形态学去噪并连接圆环
    3. 取面积最大的蓝色连通域
    4. 用最小外接圆中心作为手动翼尖
    """
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)

    lower_blue = np.array([90, 60, 60])
    upper_blue = np.array([140, 255, 255])

    blue_mask = cv2.inRange(hsv, lower_blue, upper_blue)

    kernel = np.ones((3, 3), np.uint8)
    blue_mask = cv2.morphologyEx(blue_mask, cv2.MORPH_CLOSE, kernel)
    blue_mask = cv2.dilate(blue_mask, kernel, iterations=1)

    contours, _ = cv2.findContours(blue_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    valid = [c for c in contours if cv2.contourArea(c) >= min_area]
    if not valid:
        return None

    c = max(valid, key=cv2.contourArea)
    (cx, cy), radius = cv2.minEnclosingCircle(c)
    if radius <= 0:
        return None

    return (float(cx), float(cy))


def extract_edge_profile(image, red_dot_coords=None):
    """
    Sub-pixel accurate edge extraction.
    Returns edge points with floating-point coordinates.
    """

    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    gray = gray.astype(np.float32)

    # --- 1. Canny for coarse edge mask ---
    edges = cv2.Canny(gray.astype(np.uint8), 30, 100)
    # --- NEW: remove red-dot edges (and its boundary) ---
    red_mask = make_red_mask(image)
    red_mask = cv2.dilate(red_mask, np.ones((9, 9), np.uint8), iterations=1)  # 视红点大小可调 7/9/11
    #edges[red_mask > 0] = 0
    # --- 2. Sobel gradients ---
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)

    magnitude = np.sqrt(gx**2 + gy**2) + 1e-6
    nx = gx / magnitude
    ny = gy / magnitude

    h, w = gray.shape
    edge_points = []

    # --- 3. Sub-pixel localization ---
    ys, xs = np.where(edges > 0)
    for x, y in zip(xs, ys):
        dx = nx[y, x]
        dy = ny[y, x]

        # sample gradient magnitude along normal direction
        def sample(t):
            xx = x + dx * t
            yy = y + dy * t
            if xx < 0 or yy < 0 or xx >= w - 1 or yy >= h - 1:
                return 0.0
            return cv2.getRectSubPix(magnitude, (1, 1), (xx, yy))[0, 0]

        g0 = sample(-1.0)
        g1 = sample(0.0)
        g2 = sample(1.0)

        denom = g0 - 2 * g1 + g2
        if abs(denom) < 1e-6:
            t = 0.0
        else:
            t = 0.5 * (g0 - g2) / denom

        xs_sub = x + dx * t
        ys_sub = y + dy * t

        edge_points.append((float(xs_sub), float(ys_sub)))

    # --- 4. Contour-based ordering (robust, no jump segments) ---
    edge_points = sort_points_by_contour(edges, edge_points, start_xy=red_dot_coords)

    # Return BOTH: contour (ordered) and red dot separately if you want
    return edge_points, red_dot_coords


def sort_points_by_continuity(points, start_point):
    if not points:
        return points

    pts = points.copy()

    sorted_pts = []

    current = min(
        pts,
        key=lambda p: np.hypot(p[0] - start_point[0], p[1] - start_point[1])
    )
    sorted_pts.append(current)
    pts.remove(current)

    while pts:
        next_pt = min(pts, key=lambda p: np.hypot(p[0] - current[0], p[1] - current[1]))
        sorted_pts.append(next_pt)
        pts.remove(next_pt)
        current = next_pt

    return sorted_pts

def make_red_mask(image):
    """Return binary mask (uint8 0/255) for red dot region in RGB image."""
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)

    lower_red1 = np.array([0, 100, 100])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([160, 100, 100])
    upper_red2 = np.array([180, 255, 255])

    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
    red_mask = cv2.bitwise_or(mask1, mask2)

    kernel = np.ones((3, 3), np.uint8)
    red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, kernel)
    red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN, kernel)
    return red_mask

def _rotate_points_to_start(points, start_xy):
    """Rotate ordered points so that the first point is closest to start_xy."""
    if not points:
        return points
    pts = np.asarray(points, dtype=float)
    sx, sy = float(start_xy[0]), float(start_xy[1])
    d2 = (pts[:, 0] - sx) ** 2 + (pts[:, 1] - sy) ** 2
    k = int(np.argmin(d2))
    return points[k:] + points[:k]


def sort_points_by_contour(edges, subpixel_points, start_xy=None):
    """
    Use cv2.findContours to get a true boundary order, then (optionally) map each contour
    pixel vertex to the nearest subpixel point to keep float precision.

    edges: uint8 Canny mask (0/255)
    subpixel_points: list[(float x, float y)] from your subpixel extraction
    start_xy: (x,y) to rotate the contour start (e.g. red dot)
    """
    # Make edges more connected so the contour is a single loop
    kernel = np.ones((3, 3), np.uint8)
    edges2 = cv2.dilate(edges, kernel, iterations=1)

    contours, _ = cv2.findContours(edges2, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return []

    # Pick the largest external contour
    c = max(contours, key=cv2.contourArea)
    contour_pts = c[:, 0, :]  # (N,2) int, [x,y]

    # Rotate start to be closest to start_xy (red dot)
    contour_list = [(float(x), float(y)) for x, y in contour_pts]
    if start_xy is not None:
        contour_list = _rotate_points_to_start(contour_list, start_xy)

    # If you don't care about subpixel precision for ordering, you can just return contour_list.
    # Below: map each contour vertex to nearest subpixel point (keeps float coords, keeps contour order).
    if not subpixel_points:
        return contour_list

    sp = np.asarray(subpixel_points, dtype=float)  # (M,2)
    ordered = []
    for (x, y) in contour_list:
        # vectorized nearest neighbor (O(N*M) but usually fine)
        d2 = (sp[:, 0] - x) ** 2 + (sp[:, 1] - y) ** 2
        j = int(np.argmin(d2))
        ordered.append((float(sp[j, 0]), float(sp[j, 1])))

    # Optional: remove consecutive duplicates (same subpixel chosen repeatedly)
    dedup = [ordered[0]]
    for p in ordered[1:]:
        if (p[0] - dedup[-1][0]) ** 2 + (p[1] - dedup[-1][1]) ** 2 > 1e-12:
            dedup.append(p)

    return dedup

def transform_points_by_span(contour, root, tip, force_y_positive=True, normalize_span=True):
    # 1. 平移，根点移到 (0, 0)
    contour_translated = contour - root
    
    # 2. 旋转：使得 root -> tip 对齐 x 轴
    span_x = tip[0] - root[0]
    span_y = tip[1] - root[1]
    angle = np.arctan2(span_y, span_x)  # 计算旋转角度
    M = cv2.getRotationMatrix2D((0, 0), np.degrees(angle), 1.0)
    contour_rotated = cv2.transform(contour_translated.reshape(-1, 1, 2), M).reshape(-1, 2)
    
    # 3. 归一化：将 span 变为 1
    if normalize_span:
        span_len = np.linalg.norm(tip - root)
        contour_normalized = contour_rotated / span_len
    else:
        contour_normalized = contour_rotated

    # 4. 确保翼型大部分在 y > 0 的区域
    if force_y_positive and np.mean(contour_normalized[:, 1]) < 0:
        contour_normalized[:, 1] *= -1  # 翼型上下翻转，确保 y > 0
    
    return contour_normalized
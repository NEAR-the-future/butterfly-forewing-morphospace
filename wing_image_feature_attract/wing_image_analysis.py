
import csv
import image_tool
import shape_tool
import numpy as np
from main_func import *
import matplotlib.pyplot as plt
import cv2
from scipy.signal import savgol_filter


def nearest_contour_index(contour, point):
    pts = np.asarray(contour, dtype=float).reshape(-1, 2)
    p = np.asarray(point, dtype=float).reshape(2,)
    d = np.linalg.norm(pts - p, axis=1)
    return int(np.argmin(d))

def curve_length(pts, closed=False):
    pts = np.asarray(pts, dtype=float).reshape(-1, 2)
    if len(pts) < 2:
        return 0.0

    if closed:
        d = np.diff(pts, axis=0, append=pts[:1])
    else:
        d = np.diff(pts, axis=0)

    return float(np.sum(np.hypot(d[:, 0], d[:, 1])))


def smooth_contour(contour, window_frac=0.03, polyorder=3):

    pts = np.asarray(contour, dtype=float).reshape(-1, 2)
    n = len(pts)

    if n < 7:
        P = cv2.arcLength(pts.astype(np.float32), True)
        return pts, float(P)

    win = int(max(5, round(window_frac * n)))
    if win % 2 == 0:
        win += 1

    win = min(win, n - 1 if n % 2 == 0 else n)
    if win % 2 == 0:
        win -= 1
    win = max(win, polyorder + 2 + ((polyorder + 2) % 2 == 0))

    if win >= n:
        win = n - 1 if n % 2 == 0 else n
        if win % 2 == 0:
            win -= 1

    if win <= polyorder:
        P = cv2.arcLength(pts.astype(np.float32), True)
        return pts, float(P)

    x = pts[:, 0]
    y = pts[:, 1]

    x_pad = np.r_[x[-win:], x, x[:win]]
    y_pad = np.r_[y[-win:], y, y[:win]]

    x_s = savgol_filter(x_pad, win, polyorder)
    y_s = savgol_filter(y_pad, win, polyorder)

    x_s = x_s[win:-win]
    y_s = y_s[win:-win]

    smooth_pts = np.column_stack([x_s, y_s])

    perimeter = curve_length(smooth_pts, closed=True)
    return smooth_pts, perimeter


def output_planform_smooth_compare(contour_transformed, contour_smoothed, root_transformed,
                                   tip_transformed, centroid, visual_dir, name):

    try:
        pts = np.asarray(contour_transformed, dtype=float).reshape(-1, 2)
        spt = np.asarray(contour_smoothed, dtype=float).reshape(-1, 2)

        fig, ax = plt.subplots(figsize=(10, 4))

        ax.plot(pts[:, 0], pts[:, 1], 'r-', linewidth=1.0, alpha=0.5, label='Contour (raw)')
        ax.plot(spt[:, 0], spt[:, 1], 'k-', linewidth=1.8, alpha=0.9, label='Contour (smoothed)')

        ax.plot(root_transformed[0], root_transformed[1], 'kx', markersize=10, label='Root (trans)')
        ax.plot(tip_transformed[0],  tip_transformed[1],  'k+', markersize=10, label='Tip (trans)')

        if centroid is not None and np.all(np.isfinite(centroid)):
            ax.plot(centroid[0], centroid[1], 'ko', markersize=6, label='Centroid')

        ax.set_aspect('equal', adjustable='box')
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best")
        ax.set_title(f'{name} Planform (Raw vs Smoothed)', fontsize=14, fontweight='bold')
        ax.set_xlabel('Spanwise (x)')
        ax.set_ylabel('Chordwise (y)')

        viz_path = visual_dir / f"PlatformSmoothCompare_{name}.png"
        fig.savefig(viz_path, dpi=150, bbox_inches='tight')
        plt.close(fig)

    except Exception as e:
        print(f"Visualization failed: {str(e)}")


def compute_geometry_from_contour(contour_1x2):

    area = cv2.contourArea(contour_1x2)
    perimeter = cv2.arcLength(contour_1x2, True)
    M = cv2.moments(contour_1x2)

    if M["m00"] == 0:
        cx, cy = np.nan, np.nan
    else:
        cx = M["m10"] / M["m00"]
        cy = M["m01"] / M["m00"]

    return {
        "area": float(area),
        "perimeter": float(perimeter),
        "centroid": (float(cx), float(cy)),
        "m10": float(M["m10"]), "m01": float(M["m01"]),
        "m20": float(M["m20"]), "m02": float(M["m02"]),
        "m30": float(M["m30"]), "m03": float(M["m03"]),
        "mu20": float(M["mu20"]), "mu02": float(M["mu02"]), "mu11": float(M["mu11"]),
    }



def max_chord_length(contour, n_bins=None):

    pts = np.asarray(contour, dtype=float).reshape(-1, 2)
    if len(pts) < 3:
        return np.nan

    x = pts[:, 0]
    y = pts[:, 1]

    if n_bins is None:
        n_bins = max(100, min(400, len(pts) // 2))

    xmin, xmax = np.min(x), np.max(x)
    if not np.isfinite(xmin) or not np.isfinite(xmax) or xmax <= xmin:
        return np.nan

    bins = np.linspace(xmin, xmax, n_bins + 1)
    max_chord = 0.0

    for i in range(len(bins) - 1):
        if i == len(bins) - 2:
            mask = (x >= bins[i]) & (x <= bins[i + 1])
        else:
            mask = (x >= bins[i]) & (x < bins[i + 1])

        if np.sum(mask) < 2:
            continue

        y_slice = y[mask]
        chord = float(np.max(y_slice) - np.min(y_slice))
        if chord > max_chord:
            max_chord = chord

    return max_chord if max_chord > 0 else np.nan


def polygon_area_xy(points):
    pts = np.asarray(points, dtype=float).reshape(-1, 2)
    if len(pts) < 3 or not np.all(np.isfinite(pts)):
        return 0.0

    x = pts[:, 0]
    y = pts[:, 1]
    return float(0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def area_bbox_ratio(contour, wing_area):
    pts = np.asarray(contour, dtype=float).reshape(-1, 2)
    if len(pts) < 3 or not np.isfinite(wing_area) or abs(wing_area) <= 1e-12:
        return np.nan
    if not np.all(np.isfinite(pts)):
        return np.nan

    x_min, y_min = np.min(pts, axis=0)
    x_max, y_max = np.max(pts, axis=0)
    bbox_area = float((x_max - x_min) * (y_max - y_min))

    if bbox_area <= 1e-12:
        return np.nan

    return float(abs(wing_area) / bbox_area)


def _cross2(a, b):
    return float(a[0] * b[1] - a[1] * b[0])


def _clip_polygon_by_convex_polygon(subject_pts, clip_pts, eps=1e-12):
    subject = np.asarray(subject_pts, dtype=float).reshape(-1, 2)
    clip = np.asarray(clip_pts, dtype=float).reshape(-1, 2)

    if len(subject) < 3 or len(clip) < 3:
        return np.empty((0, 2), dtype=float)
    if not np.all(np.isfinite(subject)) or not np.all(np.isfinite(clip)):
        return np.empty((0, 2), dtype=float)

    output = [p.copy() for p in subject]

    for i in range(len(clip)):
        a = clip[i]
        b = clip[(i + 1) % len(clip)]
        edge = b - a

        def inside(p):
            return _cross2(edge, p - a) >= -eps

        def intersection(p1, p2):
            direction = p2 - p1
            denom = _cross2(edge, direction)
            if abs(denom) <= eps:
                return p2.copy()
            t = -_cross2(edge, p1 - a) / denom
            t = min(1.0, max(0.0, t))
            return p1 + t * direction

        input_list = output
        output = []

        if not input_list:
            break

        prev = input_list[-1]
        prev_inside = inside(prev)

        for curr in input_list:
            curr_inside = inside(curr)

            if curr_inside:
                if not prev_inside:
                    output.append(intersection(prev, curr))
                output.append(curr)
            elif prev_inside:
                output.append(intersection(prev, curr))

            prev = curr
            prev_inside = curr_inside

    if len(output) < 3:
        return np.empty((0, 2), dtype=float)

    return np.asarray(output, dtype=float)


def tip_area_to_wing_area_ratio(contour, wing_area, tip=(1.0, 0.0), radius=0.1, n_circle=256):
    pts = np.asarray(contour, dtype=float).reshape(-1, 2)
    tip = np.asarray(tip, dtype=float).reshape(2,)

    if len(pts) < 3 or not np.isfinite(wing_area) or abs(wing_area) <= 1e-12:
        return np.nan
    if radius <= 0 or n_circle < 12:
        return np.nan
    if not np.all(np.isfinite(pts)) or not np.all(np.isfinite(tip)):
        return np.nan

    theta = np.linspace(0.0, 2.0 * np.pi, int(n_circle), endpoint=False)
    circle_poly = np.column_stack([
        tip[0] + radius * np.cos(theta),
        tip[1] + radius * np.sin(theta),
    ])

    clipped = _clip_polygon_by_convex_polygon(pts, circle_poly)
    tip_area = polygon_area_xy(clipped)

    return float(tip_area / abs(wing_area)) if tip_area > 0.0 else 0.0


def extract_two_paths_between_indices(contour, idx_a, idx_b):
    pts = np.asarray(contour, dtype=float).reshape(-1, 2)
    n = len(pts)

    if n < 3:
        return pts, pts

    if idx_a <= idx_b:
        path1 = pts[idx_a:idx_b + 1]
        path2 = np.vstack([pts[idx_b:], pts[:idx_a + 1]])
    else:
        path1 = pts[idx_a:]
        path1 = np.vstack([path1, pts[:idx_b + 1]])
        path2 = pts[idx_b:idx_a + 1]

    return path1, path2

def split_le_te_by_root_tip(contour, root_point=(0.0, 0.0), tip_point=(1.0, 0.0)):
    pts = np.asarray(contour, dtype=float).reshape(-1, 2)
    if len(pts) < 4:
        return pts, pts

    idx_root = nearest_contour_index(pts, root_point)
    idx_tip = nearest_contour_index(pts, tip_point)

    if idx_root == idx_tip:
        return pts, pts

    path1, path2 = extract_two_paths_between_indices(pts, idx_root, idx_tip)

    len1 = curve_length(path1, closed=False)
    len2 = curve_length(path2, closed=False)

    if len1 <= len2:
        le = path1
        te = path2
    else:
        le = path2
        te = path1

    return le, te

def curvature(points):
    pts = np.asarray(points, dtype=float).reshape(-1, 2)
    if len(pts) < 5:
        return np.full(len(pts), np.nan)

    x = pts[:, 0]
    y = pts[:, 1]

    dx = np.gradient(x)
    dy = np.gradient(y)
    ddx = np.gradient(dx)
    ddy = np.gradient(dy)

    denom = (dx * dx + dy * dy) ** 1.5
    denom[denom < 1e-12] = np.nan

    k = np.abs(dx * ddy - dy * ddx) / denom
    return k


def tip_curvature(contour, tip=(1.0, 0.0), radius=0.05, poly_deg=3, n_samples=200, return_details=False):
    pts = np.asarray(contour, dtype=float).reshape(-1, 2)
    tip = np.asarray(tip, dtype=float).reshape(2,)

    if len(pts) < 7:
        if return_details:
            return {
                "curvature": np.nan,
                "local_pts": np.empty((0, 2), dtype=float),
                "tip": tip,
                "radius": float(radius),
                "fallback_used": False,
                "fit_x": None,
                "fit_y": None,
            }
        return np.nan

    n = len(pts)


    d = np.linalg.norm(pts - tip, axis=1)
    idx_tip = int(np.argmin(d))

    local_idx = [idx_tip]

    acc = 0.0
    i = idx_tip
    while True:
        j = (i - 1) % n
        step = np.linalg.norm(pts[i] - pts[j])
        if acc + step > radius:
            break
        local_idx.append(j)
        acc += step
        i = j
        if j == idx_tip:
            break

    acc = 0.0
    i = idx_tip
    forward_idx = []
    while True:
        j = (i + 1) % n
        step = np.linalg.norm(pts[j] - pts[i])
        if acc + step > radius:
            break
        forward_idx.append(j)
        acc += step
        i = j
        if j == idx_tip:
            break

    # reverse(backward) + tip + forward
    backward_idx = local_idx[1:]
    backward_idx = backward_idx[::-1]
    ordered_idx = backward_idx + [idx_tip] + forward_idx

    ordered_idx = np.array(ordered_idx, dtype=int)
    local_pts = pts[ordered_idx]

    fallback_used = False

    if len(local_pts) < 7:
        fallback_used = True
        half_win = 7
        ordered_idx = [((idx_tip - k) % n) for k in range(half_win, 0, -1)] + \
                      [idx_tip] + \
                      [((idx_tip + k) % n) for k in range(1, half_win + 1)]
        ordered_idx = np.array(ordered_idx, dtype=int)
        local_pts = pts[ordered_idx]
    keep = [0]
    for i in range(1, len(local_pts)):
        if np.linalg.norm(local_pts[i] - local_pts[keep[-1]]) > 1e-10:
            keep.append(i)
    local_pts = local_pts[keep]

    if len(local_pts) < 5:
        if return_details:
            return {
                "curvature": np.nan,
                "local_pts": local_pts,
                "tip": tip,
                "radius": float(radius),
                "fallback_used": fallback_used,
                "fit_x": None,
                "fit_y": None,
            }
        return np.nan

    seg = np.diff(local_pts, axis=0)
    ds = np.hypot(seg[:, 0], seg[:, 1])
    s = np.r_[0.0, np.cumsum(ds)]

    total_len = s[-1]
    if total_len < 1e-8:
        if return_details:
            return {
                "curvature": np.nan,
                "local_pts": local_pts,
                "tip": tip,
                "radius": float(radius),
                "fallback_used": fallback_used,
                "fit_x": None,
                "fit_y": None,
            }
        return np.nan

    s_norm = s / total_len

    deg = min(poly_deg, len(local_pts) - 1)
    if deg < 2:
        if return_details:
            return {
                "curvature": np.nan,
                "local_pts": local_pts,
                "tip": tip,
                "radius": float(radius),
                "fallback_used": fallback_used,
                "fit_x": None,
                "fit_y": None,
            }
        return np.nan

    try:
        px = np.poly1d(np.polyfit(s_norm, local_pts[:, 0], deg))
        py = np.poly1d(np.polyfit(s_norm, local_pts[:, 1], deg))
    except Exception:
        if return_details:
            return {
                "curvature": np.nan,
                "local_pts": local_pts,
                "tip": tip,
                "radius": float(radius),
                "fallback_used": fallback_used,
                "fit_x": None,
                "fit_y": None,
            }
        return np.nan

    dpx = np.polyder(px, 1)
    dpy = np.polyder(py, 1)
    ddpx = np.polyder(px, 2)
    ddpy = np.polyder(py, 2)

    s_eval = np.linspace(0.0, 1.0, n_samples)
    x_fit = px(s_eval)
    y_fit = py(s_eval)

    dx = dpx(s_eval)
    dy = dpy(s_eval)
    ddx = ddpx(s_eval)
    ddy = ddpy(s_eval)

    denom = (dx * dx + dy * dy) ** 1.5
    denom[denom < 1e-12] = np.nan
    k = np.abs(dx * ddy - dy * ddx) / denom

    tip_k = float(np.nanmean(k)) if not np.all(np.isnan(k)) else np.nan

    if return_details:
        return {
            "curvature": tip_k,
            "local_pts": local_pts,
            "tip": tip,
            "radius": float(radius),
            "fallback_used": fallback_used,
            "fit_x": x_fit,
            "fit_y": y_fit,
        }

    return tip_k


def _prepare_edge_for_fit(edge_pts, n_samples=200):
    pts = np.asarray(edge_pts, dtype=float).reshape(-1, 2)
    if len(pts) < 6:
        return None, None

    pts = pts[np.argsort(pts[:, 0])]
    x = pts[:, 0]
    y = pts[:, 1]

    x_round = np.round(x, 4)
    uniq_x = np.unique(x_round)

    xg = []
    yg = []
    for ux in uniq_x:
        mask = (x_round == ux)
        if np.sum(mask) == 0:
            continue
        xg.append(np.mean(x[mask]))
        yg.append(np.mean(y[mask]))

    xg = np.asarray(xg, dtype=float)
    yg = np.asarray(yg, dtype=float)

    if len(xg) < 6:
        return None, None

    order = np.argsort(xg)
    xg = xg[order]
    yg = yg[order]

    keep = np.r_[True, np.diff(xg) > 1e-8]
    xg = xg[keep]
    yg = yg[keep]

    if len(xg) < 6 or (xg[-1] - xg[0]) < 1e-6:
        return None, None

    xs = np.linspace(xg[0], xg[-1], n_samples)
    ys = np.interp(xs, xg, yg)

    return xs, ys


def fit_edge_curve(edge_pts, poly_deg=3, n_samples=400, fit_x_range=(0.1, 0.9)):
    xs, ys = _prepare_edge_for_fit(edge_pts, n_samples=n_samples)
    if xs is None:
        return {
            "bending": np.nan,
            "x_eval": None,
            "y_fit": None,
            "coef": None,
            "curvature": None,
            "max_curv_x": np.nan,
            "max_curv_y": np.nan,
            "max_curv_value": np.nan,
        }


    x_min_fit, x_max_fit = fit_x_range
    mask = (xs >= x_min_fit) & (xs <= x_max_fit)

    if np.sum(mask) < max(6, poly_deg + 2):
        return {
            "bending": np.nan,
            "x_eval": None,
            "y_fit": None,
            "coef": None,
            "curvature": None,
            "max_curv_x": np.nan,
            "max_curv_y": np.nan,
            "max_curv_value": np.nan,
        }

    xs_fit = xs[mask]
    ys_fit = ys[mask]

    deg = min(poly_deg, len(xs_fit) - 1)
    if deg < 2:
        return {
            "bending": np.nan,
            "x_eval": None,
            "y_fit": None,
            "coef": None,
            "curvature": None,
            "max_curv_x": np.nan,
            "max_curv_y": np.nan,
            "max_curv_value": np.nan,
        }

    try:
        coef = np.polyfit(xs_fit, ys_fit, deg)
    except Exception:
        return {
            "bending": np.nan,
            "x_eval": None,
            "y_fit": None,
            "coef": None,
            "curvature": None,
            "max_curv_x": np.nan,
            "max_curv_y": np.nan,
            "max_curv_value": np.nan,
        }

    p = np.poly1d(coef)
    dp = np.polyder(p, 1)
    ddp = np.polyder(p, 2)

    x_eval = np.linspace(xs_fit[0], xs_fit[-1], n_samples)
    y_fit = p(x_eval)

    dy = dp(x_eval)
    ddy = ddp(x_eval)

    denom = (1.0 + dy ** 2) ** 1.5
    denom[denom < 1e-12] = np.nan

    k = np.abs(ddy) / denom
    bending = float(np.nanmean(k)) if not np.all(np.isnan(k)) else np.nan

    if np.all(np.isnan(k)):
        max_curv_x = np.nan
        max_curv_y = np.nan
        max_curv_value = np.nan
    else:
        idx_max = int(np.nanargmax(k))
        max_curv_x = float(x_eval[idx_max])
        max_curv_y = float(y_fit[idx_max])
        max_curv_value = float(k[idx_max])

    return {
        "bending": bending,
        "x_eval": x_eval,
        "y_fit": y_fit,
        "coef": coef,
        "curvature": k,
        "max_curv_x": max_curv_x,
        "max_curv_y": max_curv_y,
        "max_curv_value": max_curv_value,
    }

def output_edge_fit_visualization(contour_smoothed, le_pts, te_pts,
                                  le_fit, te_fit,
                                  visual_dir, name,
                                  tip_point=None,
                                  tip_radius=0.05,
                                  tip_local_pts=None,
                                  tip_curvature_value=np.nan,
                                  tip_fit_x=None,
                                  tip_fit_y=None,
                                  distal_feat=None,
                                  distal_fit=None,
                                  wing_area_bbox_ratio=np.nan,
                                  tip_area_wing_ratio=np.nan,
                                  tip_area_radius=0.1,
                                  le_offset=None,
                                  te_offset=None,
                                  distal_dx=None,
                                  distal_dy=None):
    try:
        contour_smoothed = np.asarray(contour_smoothed, dtype=float).reshape(-1, 2)
        le_pts = np.asarray(le_pts, dtype=float).reshape(-1, 2)
        te_pts = np.asarray(te_pts, dtype=float).reshape(-1, 2)

        if tip_local_pts is not None:
            tip_local_pts = np.asarray(tip_local_pts, dtype=float).reshape(-1, 2)

        if distal_feat is None:
            distal_feat = {}

        distal_seg_used = distal_feat.get("distal_segment_used", None)
        turn_point = distal_feat.get("turn_point", None)

        if distal_seg_used is not None:
            distal_seg_used = np.asarray(distal_seg_used, dtype=float).reshape(-1, 2)
        if turn_point is not None:
            turn_point = np.asarray(turn_point, dtype=float).reshape(2,)

        fig, ax = plt.subplots(figsize=(11, 5.5))

        x_scale = np.max(contour_smoothed[:, 0]) - np.min(contour_smoothed[:, 0])
        y_scale = np.max(contour_smoothed[:, 1]) - np.min(contour_smoothed[:, 1])

        if not np.isfinite(x_scale) or x_scale <= 1e-12:
            x_scale = 1.0
        if not np.isfinite(y_scale) or y_scale <= 1e-12:
            y_scale = 1.0

        if le_offset is None:
            le_offset = -0.03 * y_scale
        if te_offset is None:
            te_offset = 0.10 * y_scale

        if distal_dx is None:
            distal_dx = 0.03 * x_scale
        if distal_dy is None:
            distal_dy = 0.12 * y_scale

        ax.plot(contour_smoothed[:, 0], contour_smoothed[:, 1],
                color='0.65', linewidth=1.6, alpha=0.95, label='Smoothed contour')


        if len(le_pts) > 0:
            ax.scatter(le_pts[:, 0], le_pts[:, 1],
                       s=10, c='tab:blue', alpha=0.75, label='LE points')

        if len(te_pts) > 0:
            ax.scatter(te_pts[:, 0], te_pts[:, 1],
                       s=10, c='tab:orange', alpha=0.45, label='TE points')


        if le_fit is not None and le_fit["x_eval"] is not None:
            ax.plot(le_fit["x_eval"],
                    le_fit["y_fit"] + le_offset,
                    linestyle='--',
                    c='blue',
                    linewidth=2.2,
                    alpha=0.95,
                    label=f'LE fit (offset, bend={le_fit["bending"]:.4f})')


        if te_fit is not None and te_fit["x_eval"] is not None:
            ax.plot(te_fit["x_eval"],
                    te_fit["y_fit"] + te_offset,
                    linestyle='--',
                    c='darkorange',
                    linewidth=2.2,
                    alpha=0.95,
                    label=f'TE fit (offset, bend={te_fit["bending"]:.4f})')

            if np.isfinite(te_fit["max_curv_x"]) and np.isfinite(te_fit["max_curv_y"]):
                ax.plot(te_fit["max_curv_x"],
                        te_fit["max_curv_y"] + te_offset,
                        'o', color='darkorange', markersize=6,
                        label=f'TE max-curv x={te_fit["max_curv_x"]:.3f}')

        if distal_seg_used is not None and len(distal_seg_used) > 0:
            ax.plot(distal_seg_used[:, 0], distal_seg_used[:, 1],
                    color='limegreen', linewidth=3.0, alpha=0.95,
                    label='TE distal used (10%-95%)')

        if turn_point is not None and np.all(np.isfinite(turn_point)):
            ax.plot(turn_point[0], turn_point[1],
                    marker='D', color='purple', markersize=8,
                    label='Distal turning point')

        if distal_fit is not None and distal_fit["x_eval"] is not None:
            ax.plot(distal_fit["x_eval"] + distal_dx,
                    distal_fit["y_fit"] + distal_dy,
                    linestyle='--',
                    c='limegreen',
                    linewidth=2.4,
                    alpha=0.95,
                    label=(f'Distal fit (offset, bend={distal_fit["bending"]:.4f}, '
                           f'signed_k={distal_fit["signed_curvature"]:.4f})'))

        if tip_point is not None:
            tip_point = np.asarray(tip_point, dtype=float).reshape(2,)

            tip_circle = plt.Circle(
                (tip_point[0], tip_point[1]),
                tip_radius,
                fill=False,
                linestyle='--',
                linewidth=1.8,
                color='crimson',
                alpha=0.90,
                label=f'Tip range (r={tip_radius:.2f})'
            )
            ax.add_patch(tip_circle)

            ax.plot(tip_point[0], tip_point[1],
                    marker='*', color='crimson', markersize=12,
                    label='Tip point')

            if tip_fit_x is not None and tip_fit_y is not None:
                ax.plot(tip_fit_x, tip_fit_y,
                        color='crimson', linewidth=2.0, linestyle='-',
                        alpha=0.90, label='Tip local fit')


        ax.set_aspect('equal', adjustable='box')
        ax.grid(True, alpha=0.3)
        ax.set_title(f'{name} LE/TE fitted curves', fontsize=14, fontweight='bold')
        ax.set_xlabel('Spanwise (x)')
        ax.set_ylabel('Chordwise (y)')

  
        extra_handles = []
        extra_labels = []

        if np.isfinite(tip_curvature_value):
            extra_handles.append(plt.Line2D([], [], linestyle='None'))
            extra_labels.append(f'Tip curvature = {tip_curvature_value:.4f}')

        if distal_fit is not None and np.isfinite(distal_fit["bending"]):
            extra_handles.append(plt.Line2D([], [], linestyle='None'))
            extra_labels.append(f'Distal bending = {distal_fit["bending"]:.4f}')

        if distal_fit is not None and np.isfinite(distal_fit["signed_curvature"]):
            extra_handles.append(plt.Line2D([], [], linestyle='None'))
            extra_labels.append(f'Distal signed curvature = {distal_fit["signed_curvature"]:.4f}')

        if np.isfinite(wing_area_bbox_ratio):
            extra_handles.append(plt.Line2D([], [], linestyle='None'))
            extra_labels.append(f'Wing area / bbox area = {wing_area_bbox_ratio:.4f}')

        if np.isfinite(tip_area_wing_ratio):
            extra_handles.append(plt.Line2D([], [], linestyle='None'))
            extra_labels.append(
                f'Tip area (r={tip_area_radius:.2f}) / wing area = {tip_area_wing_ratio:.4f}'
            )

        handles, labels = ax.get_legend_handles_labels()
        handles.extend(extra_handles)
        labels.extend(extra_labels)

        ax.legend(handles, labels,
                  loc='center left',
                  bbox_to_anchor=(1.02, 0.5),
                  borderaxespad=0.,
                  frameon=True)

        viz_path = visual_dir / f"EdgeFit_{name}.png"
        fig.savefig(viz_path, dpi=150, bbox_inches='tight')
        plt.close(fig)

    except Exception as e:
        print(f"Edge fit visualization failed: {str(e)}")


def edge_bending_degree(edge_pts, poly_deg=3, n_samples=200):

    fit_res = fit_edge_curve(edge_pts, poly_deg=poly_deg, n_samples=n_samples)
    return fit_res["bending"]

def extract_distal_segment(te_pts, tip_point=(1.0, 0.0), ref_x=np.nan,
                           trim_frac=(0.10, 0.95)):

    pts = np.asarray(te_pts, dtype=float).reshape(-1, 2)
    tip = np.asarray(tip_point, dtype=float).reshape(2,)
    empty = np.empty((0, 2), dtype=float)

    if len(pts) < 8 or not np.isfinite(ref_x):
        return {
            "turn_idx": None,
            "turn_point": None,
            "tip_point": tip,
            "distal_segment": empty,
            "distal_segment_used": empty,
            "n_used": 0,
        }

    idx_turn = int(np.argmin(np.abs(pts[:, 0] - ref_x)))
    turn_pt = pts[idx_turn]

    idx_tip = int(np.argmin(np.linalg.norm(pts - tip, axis=1)))

    if idx_turn == idx_tip:
        return {
            "turn_idx": idx_turn,
            "turn_point": turn_pt,
            "tip_point": tip,
            "distal_segment": empty,
            "distal_segment_used": empty,
            "n_used": 0,
        }


    if idx_turn < idx_tip:
        seg = pts[idx_turn:idx_tip + 1]
    else:
        seg = pts[idx_tip:idx_turn + 1][::-1]

    if len(seg) < 6:
        return {
            "turn_idx": idx_turn,
            "turn_point": turn_pt,
            "tip_point": tip,
            "distal_segment": seg,
            "distal_segment_used": empty,
            "n_used": 0,
        }

    ds = np.hypot(np.diff(seg[:, 0]), np.diff(seg[:, 1]))
    s = np.r_[0.0, np.cumsum(ds)]

    if s[-1] < 1e-10:
        return {
            "turn_idx": idx_turn,
            "turn_point": turn_pt,
            "tip_point": tip,
            "distal_segment": seg,
            "distal_segment_used": empty,
            "n_used": 0,
        }

    s_norm = s / s[-1]
    lo, hi = trim_frac
    mask = (s_norm >= lo) & (s_norm <= hi)
    seg_use = seg[mask]

    return {
        "turn_idx": idx_turn,
        "turn_point": turn_pt,
        "tip_point": tip,
        "distal_segment": seg,
        "distal_segment_used": seg_use if len(seg_use) > 0 else empty,
        "n_used": int(len(seg_use)),
    }
def fit_distal_curve(distal_pts, poly_deg=3, n_samples=300):
    xs, ys = _prepare_edge_for_fit(distal_pts, n_samples=n_samples)
    if xs is None:
        return {
            "bending": np.nan,
            "signed_curvature": np.nan,
            "x_eval": None,
            "y_fit": None,
            "coef": None,
            "curvature": None,
        }

    deg = min(poly_deg, len(xs) - 1)
    if deg < 2:
        return {
            "bending": np.nan,
            "signed_curvature": np.nan,
            "x_eval": None,
            "y_fit": None,
            "coef": None,
            "curvature": None,
        }

    try:
        coef = np.polyfit(xs, ys, deg)
    except Exception:
        return {
            "bending": np.nan,
            "signed_curvature": np.nan,
            "x_eval": None,
            "y_fit": None,
            "coef": None,
            "curvature": None,
        }

    p = np.poly1d(coef)
    dp = np.polyder(p, 1)
    ddp = np.polyder(p, 2)

    x_eval = np.linspace(xs[0], xs[-1], n_samples)
    y_fit = p(x_eval)

    dy = dp(x_eval)
    ddy = ddp(x_eval)

    denom = (1.0 + dy ** 2) ** 1.5
    denom[denom < 1e-12] = np.nan

    k_signed = ddy / denom
    k_abs = np.abs(k_signed)

    bending = float(np.nanmean(k_abs)) if not np.all(np.isnan(k_abs)) else np.nan
    signed_curvature = float(np.nanmean(k_signed)) if not np.all(np.isnan(k_signed)) else np.nan

    return {
        "bending": bending,
        "signed_curvature": signed_curvature,
        "x_eval": x_eval,
        "y_fit": y_fit,
        "coef": coef,
        "curvature": k_signed,
    }


def main():
    print("=" * 60 + "\n")
    print("Butterfly wing morphology analysis")
    print("=" * 60 + "\n")

    base_dir, import_dir, visual_dir = setup_directories()
    image_files = find_image_files(import_dir)

    if not image_files:
        print(f"\nNo image files found in: {import_dir}")
        return

    print(f"\nFound {len(image_files)} image(s):")

    header = [
        "Type Number",
        "Name",
        "Area",
        "WingArea_BBoxAreaRatio",
        "TipArea_R0p1_WingAreaRatio",
        "Roundness",
        "LE_TE_ratio",
        "TipCurvature",
        "LE_Bending",
        "TE_Bending",
        "TE_MaxCurvX",
        "TE_Distal_Bending",
        "TE_Distal_SignedCurvature",
    ]

    result = []
    FAMILY_CODE_MAP = {
        "Hesperiidae": 1,
        "Lycaenidae": 2,
        "Papilionidae": 3,
        "Pieridae": 4,
        "Biblidinae": 5,
        "Charaxinae": 6,
        "Danainae": 7,
        "Heliconiinae": 8,
        "Limenitidinae": 9,
        "Nymphalinae": 10,
        "Satyrinae": 11,
        "Parnassiinae": 12,
        "Riodinidae": 13,
    }

    def encode_family_name(name):

        name_str = str(name)

        for family, code in FAMILY_CODE_MAP.items():
            if family in name_str:
                return code

        return np.nan
    
    for image_path in image_files:
        out = process_single_image(image_path, base_dir)
        if out is None:
            continue

        edge_points, wing_root, manual_tip = out
        if manual_tip is not None:
            wing_tip = manual_tip
        else:
                    wing_tip = shape_tool.tip_locate(
                        edge_points,
                        wing_root,
                        bending_threshold=35,
                        window_size=15
                    )

        if wing_tip is None:
            print(f"ERROR: wing_tip is None for {image_path.stem}")
            continue

        original = image_tool.import_image(str(image_path))
        output_sections(
            original=original,
            edge_points=edge_points,
            wing_root=wing_root,
            wing_tip=wing_tip,
            visual_dir=visual_dir,
            name=image_path.stem
        )

        contour_pts = np.asarray(edge_points, dtype=np.float32).reshape(-1, 2)
        root = np.asarray(wing_root, dtype=np.float32).reshape(2,)
        tip = np.asarray(wing_tip, dtype=np.float32).reshape(2,)

        contour_t = image_tool.transform_points_by_span(contour_pts, root, tip)
        contour_1x2 = np.asarray(contour_t, dtype=np.float32).reshape(-1, 1, 2)

        geo = compute_geometry_from_contour(contour_1x2)

        wing_area = geo["area"]
        centroid = np.array(geo["centroid"], dtype=float)
        wing_area_bbox_ratio = area_bbox_ratio(contour_t, wing_area)
        tip_area_wing_ratio = tip_area_to_wing_area_ratio(
            contour_t,
            wing_area,
            tip=(1.0, 0.0),
            radius=0.1
        )

        mo1_y = geo["m10"]   # ∬ x dA
        mo1_x = geo["m01"]   # ∬ y dA
        mo2_y = geo["m20"]   # ∬ x^2 dA
        mo2_x = geo["m02"]   # ∬ y^2 dA

        contour_s, P_smooth = smooth_contour(contour_t)
        perimeter = P_smooth

        roundness = 4.0 * np.pi * wing_area / (P_smooth ** 2) if P_smooth > 0 else np.nan
        max_chord = max_chord_length(contour_s)

        le_pts, te_pts = split_le_te_by_root_tip(
            contour_s,
            root_point=(0.0, 0.0),
            tip_point=(1.0, 0.0)
        )

        le_len = curve_length(le_pts, closed=False)
        te_len = curve_length(te_pts, closed=False)
        LE_TE_ratio = le_len / te_len if te_len > 1e-12 else np.nan

        tip_info = tip_curvature(
                contour_s,
                tip=(1.0, 0.0),
                radius=0.05,
                poly_deg=3,
                n_samples=200,
                return_details=True
            )
        tip_k = tip_info["curvature"]

        le_fit = fit_edge_curve(le_pts, poly_deg=3, n_samples=400, fit_x_range=(0.1, 0.9))
        te_fit = fit_edge_curve(te_pts, poly_deg=3, n_samples=400, fit_x_range=(0.1, 0.9))

        le_bending = le_fit["bending"]
        te_bending = te_fit["bending"]

        le_maxcurv_x = le_fit["max_curv_x"]
        te_maxcurv_x = te_fit["max_curv_x"]

        distal_feat = extract_distal_segment(
            te_pts,
            tip_point=(1.0, 0.0),
            ref_x=te_maxcurv_x,
            trim_frac=(0.10, 0.95)
        )

        distal_fit = fit_distal_curve(
            distal_feat["distal_segment_used"],
            poly_deg=3,
            n_samples=300
        )

        te_distal_bending = distal_fit["bending"]
        te_distal_signed_curvature = distal_fit["signed_curvature"]
        root_t = (0.0, 0.0)
        tip_t = (1.0, 0.0)

        # output_planform(
        #     contour_transformed=contour_t,
        #     root_transformed=root_t,
        #     tip_transformed=tip_t,
        #     centroid=centroid,
        #     visual_dir=visual_dir,
        #     name=image_path.stem
        # )

        # output_planform_smooth_compare(
        #     contour_transformed=contour_t,
        #     contour_smoothed=contour_s,
        #     root_transformed=root_t,
        #     tip_transformed=tip_t,
        #     centroid=centroid,
        #     visual_dir=visual_dir,
        #     name=image_path.stem
        # )

        output_edge_fit_visualization(
            contour_smoothed=contour_s,
            le_pts=le_pts,
            te_pts=te_pts,
            le_fit=le_fit,
            te_fit=te_fit,
            visual_dir=visual_dir,
            name=image_path.stem,
            tip_point=(1.0, 0.0),
            tip_radius=tip_info["radius"],
            tip_local_pts=tip_info["local_pts"],
            tip_curvature_value=tip_info["curvature"],
            tip_fit_x=tip_info["fit_x"],
            tip_fit_y=tip_info["fit_y"],
            distal_feat=distal_feat,
            distal_fit=distal_fit,
            wing_area_bbox_ratio=wing_area_bbox_ratio,
            tip_area_wing_ratio=tip_area_wing_ratio,
            tip_area_radius=0.1
        )

        sample_name = str(image_path.stem)
        family_code = encode_family_name(sample_name)

        row_data = [
            int(family_code) if np.isfinite(family_code) else np.nan,
            sample_name,
            float(wing_area) if np.isfinite(wing_area) else np.nan,
            float(wing_area_bbox_ratio) if np.isfinite(wing_area_bbox_ratio) else np.nan,
            float(tip_area_wing_ratio) if np.isfinite(tip_area_wing_ratio) else np.nan,
            float(roundness) if np.isfinite(roundness) else np.nan,
            float(LE_TE_ratio) if np.isfinite(LE_TE_ratio) else np.nan,
            float(tip_k) if np.isfinite(tip_k) else np.nan,
            float(le_bending) if np.isfinite(le_bending) else np.nan,
            float(te_bending) if np.isfinite(te_bending) else np.nan,
            float(te_maxcurv_x) if np.isfinite(te_maxcurv_x) else np.nan,
            float(te_distal_bending) if np.isfinite(te_distal_bending) else np.nan,
            float(te_distal_signed_curvature) if np.isfinite(te_distal_signed_curvature) else np.nan,
        ]
        result.append(row_data)

    with open("summary_11.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(result)

    print("\nDone writing to CSV")


if __name__ == "__main__":
    main()

import traceback
import image_tool
from main_func import *
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

def setup_directories():

    base_dir = Path(__file__).parent
    import_dir = base_dir / "wing_import"
    visual_dir = base_dir / "edge_visual_data"
    
    
    import_dir.mkdir(exist_ok=True)
    visual_dir.mkdir(exist_ok=True)
    
    return base_dir, import_dir, visual_dir



def find_image_files(import_dir):

    image_files = []
    

    for file_path in import_dir.iterdir():
        if not file_path.is_file():
            continue
            

        if file_path.suffix.lower() == '.png':
            image_files.append(file_path)
    
    return sorted(image_files)



def process_single_image(image_path, base_dir):

    print(f"\n{'='*60}")
    print(f"Processing: {image_path.name}")
    
    try:
 
        original = image_tool.import_image(str(image_path))

        red_dot = image_tool.detect_red_dot(original)
        
        if not red_dot:
            print("WARNING: No red dot detected.\nContinuing without wing root marker...")
        
        # Extract wing edges
        edge_points,reddot = image_tool.extract_edge_profile(
            original, 
            red_dot_coords=red_dot
        )
        
        if not edge_points:
            print("ERROR: No edge points found. Check image quality.")
            return None
        
        output_csv = base_dir / f"wing_coordinate/{image_path.stem}_edge_coordinates.csv"
        with open(output_csv, 'w') as f:
            f.write("X,Y,is_wing_root\n")
            for x, y in edge_points:
                is_root = "YES" if (red_dot and (x, y) == red_dot) else "NO"
                f.write(f"{x},{y},{is_root}\n")
        
        print(f"<< Coordinates saved")
        manual_tip = image_tool.detect_blue_circle(original)
        return edge_points, red_dot, manual_tip
        
    except Exception as e:
        print(f"ERROR processing {image_path.name}: {str(e)}")
        traceback.print_exc()
        return None


def output_sections(original, edge_points, wing_root, wing_tip, visual_dir, name):

    try:
        fig, ax = plt.subplots(1, 1, figsize=(10, 6))
        ax.imshow(original)

        # edge points
        if edge_points:
            x_vals, y_vals = zip(*edge_points)
            ax.scatter(x_vals, y_vals, s=6, c='red', alpha=0.6, label='Extracted contour pts')

        # root & tip & span line
        ax.plot([wing_root[0], wing_tip[0]], [wing_root[1], wing_tip[1]],
                'y-', linewidth=2.5, label='Span line (root->tip)')
        ax.plot(wing_root[0], wing_root[1], 'kx', markersize=10, label='Root')
        ax.plot(wing_tip[0],  wing_tip[1],  'k+', markersize=10, label='Tip')

        ax.set_title(f'Extraction Check: {name}', fontsize=14, fontweight='bold')
        ax.axis('off')
        ax.legend(loc="best")
        plt.tight_layout()

        viz_path = visual_dir / f"Section_{name}.png"
        fig.savefig(viz_path, dpi=150, bbox_inches='tight')
        plt.close(fig)

    except Exception as e:
        print(f" Visualization failed: {str(e)}")


def output_planform(contour_transformed, root_transformed, tip_transformed, centroid, visual_dir, name):

    try:
        pts = np.asarray(contour_transformed, dtype=float).reshape(-1, 2)

        fig, ax = plt.subplots(figsize=(10, 4))

        ax.plot(pts[:, 0], pts[:, 1], 'r-', linewidth=1.5, label='Contour (rot+norm)')

        # root=(0,0), tip=(1,0)
        ax.plot(root_transformed[0], root_transformed[1], 'kx', markersize=10, label='Root (trans)')
        ax.plot(tip_transformed[0],  tip_transformed[1],  'k+', markersize=10, label='Tip (trans)')

        if centroid is not None and np.all(np.isfinite(centroid)):
            ax.plot(centroid[0], centroid[1], 'ko', markersize=6, label='Centroid')

        ax.set_aspect('equal', adjustable='box')
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best")
        ax.set_title(f'{name} Planform (Span-aligned, Normalized)', fontsize=14, fontweight='bold')
        ax.set_xlabel('Spanwise (x)')
        ax.set_ylabel('Chordwise (y)')

        viz_path = visual_dir / f"Platform_{name}.png"
        fig.savefig(viz_path, dpi=150, bbox_inches='tight')
        plt.close(fig)

    except Exception as e:
        print(f" Visualization failed: {str(e)}")
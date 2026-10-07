

import project_summary_input_to_fine_umap as projection


if __name__ == "__main__":
    projection.DEFAULT_PROJECTION_SUBDIR = "summary_input_projection_warning_only"
    projection.main(ood_policy=projection.OOD_POLICY_WARNING_ONLY)

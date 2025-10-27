import zarr
import zarr.storage
import napari
import numpy as np
from scipy.ndimage import zoom
import SimpleITK as sitk
import math
import sys
import os
import time
import argparse
from loguru import logger


def process_data(PATH_FILE):
    VOXEL_SPACING = (1.018, 0.1842, 0.1842)
    T_INDEX = 0

    DOWNSAMPLE_FACTOR = 0.25 

    ANGLE_DEGREE = 0.0  
    ANGLE_RADIAN = math.pi * ANGLE_DEGREE / 180.0
    AXIS_ROTATION = 'Y'

    store = None
    t_total_start = time.time()
    try:
        t0 = time.time()
        if not os.path.exists(PATH_FILE):
            logger.error(f"ERRO: File '{PATH_FILE}' not found!")
            sys.exit(1)

        data = zarr.open(PATH_FILE, mode='r')

        view0_3d = data[T_INDEX, 0, :, :, :].astype(np.float32)
        view1_3d = data[T_INDEX, 1, :, :, :].astype(np.float32)

        logger.info(f"Downsampling for a scale of {DOWNSAMPLE_FACTOR}")
        factors = (DOWNSAMPLE_FACTOR, DOWNSAMPLE_FACTOR, DOWNSAMPLE_FACTOR)
        view0_reg = zoom(view0_3d, factors, order=1)
        view1_reg = zoom(view1_3d, factors, order=1)
        new_spacing = [s / DOWNSAMPLE_FACTOR for s in VOXEL_SPACING]
        del view0_3d
        del view1_3d
        logger.info(f"  Preprocessing time: {time.time() - t0:.2f}s")

        logger.info("\n--- Getting Ready for Registration ---")
        t0 = time.time()

        fixed_image = sitk.GetImageFromArray(view0_reg)
        moving_image = sitk.GetImageFromArray(view1_reg)
        fixed_image.SetSpacing(new_spacing)
        moving_image.SetSpacing(new_spacing)

        R = sitk.ImageRegistrationMethod()
        
        R.SetMetricAsMattesMutualInformation(numberOfHistogramBins=50)
        
        R.SetOptimizerAsGradientDescent(
            learningRate=1.0, numberOfIterations=300, 
            estimateLearningRate=R.EachIteration
        )
        R.SetOptimizerScalesFromPhysicalShift()
        R.SetInterpolator(sitk.sitkLinear)

        initial_transform = sitk.Euler3DTransform()
        image_size = fixed_image.GetSize()
        center_pixels = [ (s-1)/2.0 for s in image_size ]
        center_physical = fixed_image.TransformContinuousIndexToPhysicalPoint(center_pixels)
        initial_transform.SetCenter(center_physical)

        logger.info(f"Setting initial angle: {ANGLE_DEGREE} degrees on axis {AXIS_ROTATION}")
        initial_transform.SetRotation(0, ANGLE_RADIAN, 0)

        R.SetInitialTransform(initial_transform)
        final_transform = R.Execute(fixed_image, moving_image)

        logger.info(f"  Registration time (SITK Execute): {time.time() - t0:.2f}s")

        logger.info("Applying final transformation (warping)...")
        view1_warped_sitk = sitk.Resample(
            moving_image, fixed_image, final_transform,
            sitk.sitkLinear, 0.0, moving_image.GetPixelID()
        )
        view1_warped_np = sitk.GetArrayFromImage(view1_warped_sitk)

        logger.success("Initializing Napari for final visualization.")
        viewer = napari.Viewer()

        viewer.add_image(
            view0_reg, 
            name='View 0 (Subsampled)', 
            colormap='gray', 
            blending='additive',
            scale=new_spacing
        )

        viewer.add_image(
            view1_warped_np, 
            name='View 1 (Aligned)', 
            colormap='magenta', 
            blending='additive',
            scale=new_spacing
        )

        viewer.add_image(
            view1_reg, 
            name='View 1 (Original)', 
            colormap='green', 
            blending='additive', 
            visible=False,
            scale=new_spacing
        )

        napari.run()

    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        if store is not None:
            store.close()
            logger.info("Store (ZIP file) closed.")
        logger.info(f"Total execution time: {time.time() - t_total_start:.2f}s")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CZ Biohub Code Challenge - Gabriela Barbosa Silva")
    parser.add_argument('--input', type=str, help='Path to the Zarr file')
    args = parser.parse_args()

    PATH_FILE = args.input
    process_data(PATH_FILE)
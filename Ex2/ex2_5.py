import sys
import logging

import yaml
import cv2
import easyocr
import numpy as np

from ex2_3 import pdf_to_image, find_title_boxes, draw_box, run_ocr

# Logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

# Read configuration from config.yml
with open("config.yml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

GREEN = tuple(config["colors"]["green"])
ROI_PADDING = config["pipe_detection"]["wc_roi_padding"]
KERNEL_SIZE = config["pipe_detection"]["pipe_kernel_size"]
MIN_PIPE_AREA = config["pipe_detection"]["min_pipe_area"]
WC_REGEX = config["pipe_detection"]["wc_regex"]
TARGET_PIPE_LABEL = config["pipe_detection"]["target_pipe_label"]
BOX_THICKNESS = config["drawing"]["box_thickness"]


def get_wc_rois(img, ocr_results):
    """Find WC text bounding boxes and calculate padded ROIs"""
    import re

    wc_pattern = re.compile(WC_REGEX, re.IGNORECASE)
    wc_boxes = find_title_boxes(ocr_results, target_text=wc_pattern)

    rois = []
    h, w = img.shape[:2]

    for box in wc_boxes:
        (x1, y1), (x2, y2) = box
        # Calculate ROI bounding box
        roi_x1 = int(max(0, x1 - ROI_PADDING))
        roi_y1 = int(max(0, y1 - ROI_PADDING))
        roi_x2 = int(min(w, x2 + ROI_PADDING))
        roi_y2 = int(min(h, y2 + ROI_PADDING))

        rois.append({"text_box": box, "roi_rect": (roi_x1, roi_y1, roi_x2, roi_y2)})
    return rois


def extract_thick_pipes(roi_img):
    """Isolate thick lines in the image using morphological operations"""
    gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)

    # Adaptive threshold to handle different shadings in the PDF
    thresh = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        blockSize=21,
        C=4,
    )

    # Opening to erase thin lines and keep thick pipes
    # Using a structural element of KERNEL_SIZE x KERNEL_SIZE
    kernel = np.ones((KERNEL_SIZE, KERNEL_SIZE), np.uint8)
    opened = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)

    return opened


def find_label_in_roi(roi_img, reader, target_text):
    """
    Try to find target_text in roi_img with 8 rotation angles (0, 45, 90, 135, 180, 225, 270, 315).
    Returns (cx, cy) in ROI coordinates or None.
    """
    h_roi, w_roi = roi_img.shape[:2]
    angles = [0, 45, 90, 135, 180, 225, 270, 315]

    for angle in angles:
        M = None
        if angle == 0:
            rotated = roi_img
        elif angle == 90:
            rotated = cv2.rotate(roi_img, cv2.ROTATE_90_CLOCKWISE)
        elif angle == 180:
            rotated = cv2.rotate(roi_img, cv2.ROTATE_180)
        elif angle == 270:
            rotated = cv2.rotate(roi_img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        else:
            # General rotation for angles like 45, 135, etc.
            center = (w_roi / 2.0, h_roi / 2.0)
            M = cv2.getRotationMatrix2D(
                center, -angle, 1.0
            )  # -angle because cv2 is CCW
            rotated = cv2.warpAffine(roi_img, M, (w_roi, h_roi))

        # Run OCR
        results = reader.readtext(rotated)
        text_found = [res[1] for res in results]
        logging.info(f"OCR at {angle}° found: {text_found}")

        for bbox, text, prob in results:
            clean_text = text.replace(" ", "").lower()
            if target_text.lower() in clean_text:
                logging.info(
                    f"Matched '{target_text}' in '{text}' at {angle}° (prob={prob:.2f})"
                )

                # Get center in rotated ROI (bbox is list of [x, y])
                rx_sum = sum([p[0] for p in bbox]) / 4.0
                ry_sum = sum([p[1] for p in bbox]) / 4.0

                # Map back to 0° ROI coordinates
                if angle == 0:
                    return (rx_sum, ry_sum)
                elif angle == 90:
                    return (ry_sum, h_roi - 1 - rx_sum)
                elif angle == 180:
                    return (w_roi - 1 - rx_sum, h_roi - 1 - ry_sum)
                elif angle == 270:
                    return (w_roi - 1 - ry_sum, rx_sum)
                elif M is not None:
                    M_inv = cv2.invertAffineTransform(M)
                    pt = np.array([[rx_sum, ry_sum]], dtype=np.float32)
                    pt_transformed = cv2.transform(np.array([pt]), M_inv)
                    return (pt_transformed[0][0][0], pt_transformed[0][0][1])

    return None


def detect_and_draw_pipes(image_input, output_path: str):
    """
    Pipeline for detecting waste pipes:
    1. Run OCR to locate "WC" labels.
    2. Crop Regions of Interest (ROI) around each WC.
    3. Find "75" pipe labels using 8-angle rotational OCR (45° steps).
    4. Isolate thick lines using Morphology (Opening).
    5. Filter and identify the closest pipe segment to each "75" label.
    6. Draw the identified pipe segments in Green.
    """
    logging.info("=" * 55)
    logging.info(f"Output image: {output_path}")
    logging.info("=" * 55)

    if isinstance(image_input, str):
        img = cv2.imread(image_input)
    elif isinstance(image_input, list):
        img = image_input[0]
    else:
        img = image_input

    result = img.copy()

    # Run OCR to find WCs
    logging.info(f"[1/3] Running OCR to find '{WC_REGEX}'...")
    reader = easyocr.Reader(["en"])
    ocr_results = run_ocr(img, reader)

    rois = get_wc_rois(img, ocr_results)
    logging.info(f"Found {len(rois)} 'WC' locations")

    # Extract thick pipes inside each ROI
    logging.info(f"[2/3] Extracting thick pipes within {ROI_PADDING}px of WCs...")
    total_pipes_drawn = 0

    for roi_data in rois:
        rx1, ry1, rx2, ry2 = roi_data["roi_rect"]
        roi_crop = img[ry1:ry2, rx1:rx2]

        # Isolate thick pipes
        pipe_mask = extract_thick_pipes(roi_crop)

        # Try to find "75" label for proximity filtering
        label_pos = find_label_in_roi(roi_crop, reader, TARGET_PIPE_LABEL)

        # Find contours of the thick pipes
        contours, _ = cv2.findContours(
            pipe_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        valid_contours = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > MIN_PIPE_AREA:
                valid_contours.append(cnt)

        if label_pos and valid_contours:
            # Find the closest contour to the label
            best_cnt = None
            min_dist = float("inf")
            lx, ly = label_pos

            for cnt in valid_contours:
                # Find minimum distance from label to any point in contour
                points = cnt.reshape(-1, 2)
                dists = np.linalg.norm(points - np.array([lx, ly]), axis=1)
                d = np.min(dists)
                if d < min_dist:
                    min_dist = d
                    best_cnt = cnt

            if best_cnt is not None:
                cnt_offset = best_cnt + np.array([rx1, ry1])
                cv2.drawContours(result, [cnt_offset], -1, GREEN, BOX_THICKNESS)
                total_pipes_drawn += 1
        else:
            if not label_pos:
                logging.warning(
                    f"Label '{TARGET_PIPE_LABEL}' not found near WC at ({rx1}, {ry1})"
                )
            if not valid_contours:
                logging.warning(f"No thick pipes found near WC at ({rx1}, {ry1})")

    # Save results 
    logging.info("[3/3] Saving output...")
    cv2.imwrite(output_path, result)
    logging.info(f"Successfully saved result image: {output_path}")
    logging.info(f"Total pipe segments drawn: {total_pipes_drawn}")

    return result


# ──────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────
if __name__ == "__main__":
    pdf_input = "input_file/demo_cad_24.pdf"
    INPUT_IMAGE = pdf_to_image(pdf_input, dpi=400)
    OUTPUT_IMAGE = "output_file/2-5-result_pipes.jpg"

    detect_and_draw_pipes(INPUT_IMAGE, OUTPUT_IMAGE)

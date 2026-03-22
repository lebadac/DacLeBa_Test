import re
import sys
import os
import yaml
import logging

import cv2
import numpy as np
import easyocr

from ex2_3 import pdf_to_image, find_title_boxes, draw_box, run_ocr

# Logging
logging.basicConfig(level=logging.INFO)
# Read configuration from config.yml
with open("config.yml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

PURPLE = tuple(config["colors"]["purple"])
GREEN = tuple(config["colors"]["green"])
BOX_THICKNESS = config["drawing"]["box_thickness"]
LABEL_FONT_SCALE = float(config["drawing"]["label_font_scale"])
LABEL_THICKNESS = config["drawing"]["label_thickness"]

MIN_ROOM_AREA_PX = config["room_detection"]["min_room_area_px"]
MAX_ROOM_RATIO = float(config["room_detection"]["max_room_ratio"])

OCR_PADDING = config["ocr"]["padding"]

# Regex for area label detection (e.g., "12.5m2", "30㎡", "25 M2"...)
AREA_RE_PATTERN = config["ocr"]["area_regex"]
AREA_RE = re.compile(AREA_RE_PATTERN, re.IGNORECASE)

def preprocess(img: np.ndarray):
    """
    Convert to grayscale -> inverse binary threshold
    (dark walls -> white, light background -> black) -> dilate to connect broken lines.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Adaptive threshold for scanned images with uneven lighting
    thresh = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        blockSize=21,
        C=4,
    )

    # Dilate to connect broken wall segments
    kernel = np.ones((3, 3), np.uint8)
    dilated = cv2.dilate(thresh, kernel, iterations=2)

    return gray, thresh, dilated

def find_room_contours(dilated: np.ndarray, total_area: int):
    """
    Find all contours, filter by area to keep regions
    that are likely rooms / apartments.
    Returns a list of bounding rects (x, y, w, h).
    """
    contours, _ = cv2.findContours(dilated, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    rooms = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        area = w * h
        ratio = area / total_area

        if MIN_ROOM_AREA_PX < area and ratio < MAX_ROOM_RATIO:
            # Additional filter: aspect ratio (avoid thin straight lines)
            aspect = max(w, h) / (min(w, h) + 1e-5)
            if aspect < 10:
                rooms.append((x, y, w, h))

    # Remove overlapping boxes (high IoU)
    rooms = non_max_suppression(rooms, iou_threshold=0.4)
    return rooms

def non_max_suppression(boxes, iou_threshold=0.4):
    """Keep a representative box when multiple boxes overlap."""
    if not boxes:
        return []

    boxes_arr = np.array(boxes, dtype=float)
    x1 = boxes_arr[:, 0]
    y1 = boxes_arr[:, 1]
    x2 = boxes_arr[:, 0] + boxes_arr[:, 2]
    y2 = boxes_arr[:, 1] + boxes_arr[:, 3]
    areas = (x2 - x1) * (y2 - y1)

    order = areas.argsort()[::-1]
    keep = []

    while order.size > 0:
        i = order[0]
        keep.append(i)

        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])

        inter_w = np.maximum(0, xx2 - xx1)
        inter_h = np.maximum(0, yy2 - yy1)
        inter = inter_w * inter_h
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-5)

        order = order[1:][iou < iou_threshold]

    return [boxes[k] for k in keep]

def draw_boxes(result: np.ndarray, rooms: list, labels=None):
    """Draw a purple bounding box on the result image."""
    for idx, (x, y, w, h) in enumerate(rooms, start=1):
        box_coords = ((x, y), (x + w, y + h))
        draw_box(result, box_coords, color=PURPLE, thickness=BOX_THICKNESS)

        # Room number label
        label_text = f"Room {idx}"
        (tw, th), baseline = cv2.getTextSize(
            label_text, cv2.FONT_HERSHEY_SIMPLEX, LABEL_FONT_SCALE, LABEL_THICKNESS
        )
        lx = max(x, 0)
        ly = max(y - 4, th + 4)
        cv2.rectangle(
            result,
            (lx, ly - th - baseline - 2),
            (lx + tw + 4, ly + baseline),
            PURPLE,
            -1,
        )
        cv2.putText(
            result,
            label_text,
            (lx + 2, ly - baseline),
            cv2.FONT_HERSHEY_SIMPLEX,
            LABEL_FONT_SCALE,
            (255, 255, 255),
            LABEL_THICKNESS,
            cv2.LINE_AA,
        )

    # Draw small green box around OCR label (if available - from find_title_boxes)
    if labels:
        for lbl in labels:
            draw_box(result, lbl, color=GREEN, thickness=2)

    return result

def detect_rooms(image_input, output_path: str, use_ocr: bool = True):
    """
    Complete room detection pipeline:
    1. Read and preprocess the floor plan image (grayscale, thresholding).
    2. Identify candidate room boundaries using contour detection and filtering.
    3. (Optional) Run OCR to locate area labels (e.g., "m²") within the plan.
    4. Match "m²" labels with room contours and apply NMS.
    5. Draw confirmed room areas with purple bounding boxes and save the output.
    """
    logging.info("=" * 55)
    logging.info(f"Output image: {output_path}")
    logging.info("=" * 55)

    # Handle if passed a file path, a numpy array, or a list
    if isinstance(image_input, str):
        img = cv2.imread(image_input)
        if img is None:
            logging.error(f"Cannot open image: {image_input}")
            sys.exit(1)
    elif isinstance(image_input, list):
        img = image_input[0]  # Get the first page if it's a list (from PDF)
    else:
        img = image_input

    h, w = img.shape[:2]
    total_area = h * w
    logging.info(f"Image size: {w} x {h} px ({total_area:,} px²)")

    result = img.copy()
    gray, thresh, dilated = preprocess(img)

    # Find all valid contours in the image 
    logging.info("[1/3] Finding all contours...")
    all_contours, _ = cv2.findContours(dilated, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    valid_contours = []
    for cnt in all_contours:
        x, y, w, h = cv2.boundingRect(cnt)
        area = w * h
        ratio = area / total_area
        aspect = max(w, h) / (min(w, h) + 1e-5)
        if MIN_ROOM_AREA_PX < area and ratio < MAX_ROOM_RATIO and aspect < 10:
            valid_contours.append(cnt)
    logging.info(f"Found {len(valid_contours)} valid contours")

    # OCR – find m² labels using function from ex2_3
    logging.info("[2/3] Detecting m² labels using OCR from ex2_3...")
    ocr_labels = []
    if use_ocr:
        try:
            reader = easyocr.Reader(["en"])
            ocr_results = run_ocr(img, reader)
            ocr_labels = find_title_boxes(ocr_results, target_text=AREA_RE)
            logging.info(f"Found {len(ocr_labels)} 'm²' labels")
        except Exception as e:
            logging.error(f"EasyOCR Error: {e}")
    else:
        logging.info("[SKIPPED] use_ocr parameter is False")

    # Keep only contours that contain at least one m² label center 
    logging.info("[3/3] Filtering contours containing m² labels...")
    all_rooms = []
    for cnt in valid_contours:
        for box in ocr_labels:
            (x1, y1), (x2, y2) = box
            cx, cy = float(x1 + (x2 - x1) // 2), float(y1 + (y2 - y1) // 2)
            if cv2.pointPolygonTest(cnt, (cx, cy), measureDist=False) >= 0:
                x, y, w, h = cv2.boundingRect(cnt)
                all_rooms.append((x, y, w, h))
                break  # Label matched, no need to check other labels

    all_rooms = non_max_suppression(all_rooms, iou_threshold=0.35)
    logging.info(f"Total room bounding boxes with m²: {len(all_rooms)}")

    # Draw & Save
    result = draw_boxes(result, all_rooms, ocr_labels)
    cv2.imwrite(output_path, result)
    logging.info(f"Successfully saved result image: {output_path}")
    logging.info(f"Total purple bounding boxes: {len(all_rooms)}")

    return result, all_rooms

if __name__ == "__main__":

    pdf_input = "input_file/demo_cad_24.pdf"
    INPUT_IMAGE = pdf_to_image(pdf_input, dpi=400)
    OUTPUT_IMAGE = "output_file/2-4-result_rooms.jpg"

    detect_rooms(INPUT_IMAGE, OUTPUT_IMAGE, use_ocr=True)

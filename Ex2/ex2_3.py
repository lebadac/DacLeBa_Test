import logging
import os 

import cv2
import numpy as np
import easyocr
from pypdf import PdfReader
from pdf2image import convert_from_path

logging.basicConfig(level=logging.INFO)

def pdf_to_image(pdf_path, dpi=300):
    """
    Convert PDF file to image.
    """
    logging.info("Converting PDF to image...")
    pages = convert_from_path(pdf_path, dpi=dpi)

    images = []
    for page in pages:
        img = np.array(page)
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        images.append(img)

    logging.info(f"Conversion done: {len(images)} pages")
    return images

def run_ocr(img, reader):
    """
    Run OCR on the image.
    """
    logging.info("Running OCR...")
    results = reader.readtext(img)
    logging.info(f"OCR detected {len(results)} text regions")
    return results

def find_title_boxes(ocr_results, target_text="jib"):
    """
    Find specific text in the OCR results. target_text can be a string or a compiled regex pattern.
    """
    logging.info(f"Finding '{target_text}' text...")

    boxes = []

    for bbox, text, prob in ocr_results:
        text_lower = text.lower()
        clean_text = text.replace(" ", "").lower()
        
        is_match = False
        if hasattr(target_text, 'search'):
            # If target_text is a regex pattern (e.g. AREA_RE)
            if target_text.search(clean_text) or target_text.search(text_lower):
                is_match = True
        else:
            # If target_text is a normal string
            if target_text.lower() in text_lower:
                is_match = True

        if is_match:
            logging.info(f"Found: {text} (conf={prob:.2f})")

            top_left = tuple(map(int, bbox[0]))
            bottom_right = tuple(map(int, bbox[2]))

            boxes.append((top_left, bottom_right))

    return boxes

def merge_boxes(boxes):
    """
    Merge bounding boxes.
    """
    logging.info("Merging bounding boxes...")

    x1 = min(box[0][0] for box in boxes)
    y1 = min(box[0][1] for box in boxes)
    x2 = max(box[1][0] for box in boxes)
    y2 = max(box[1][1] for box in boxes)

    return (x1, y1), (x2, y2)

def draw_box(img, box, color=(0, 140, 255), thickness=3):
    """
    Draw bounding box on the image.
    """
    logging.info("Drawing bounding box...")

    top_left, bottom_right = box

    cv2.rectangle(img, top_left, bottom_right, color, thickness)

    return img

def process_pdf(pdf_path, output_dir="output_file", target_text="jib"):
    """
    End-to-end function to process PDF, find targeted text, draw bounding box and save to output directory.
    """
    os.makedirs(output_dir, exist_ok=True)
    # Read PDF
    logging.info(f"Reading PDF file: {pdf_path}")
    reader = PdfReader(pdf_path)
    logging.info(f"Number of pages: {len(reader.pages)}")
    # Convert PDF to multiple images
    images = pdf_to_image(pdf_path)
    # Run OCR model initialization just ONE time
    ocr_reader = easyocr.Reader(["en"])
    
    results = []
    # Loop through each page
    for i, img in enumerate(images):
        page_num = i + 1
        logging.info(f"--- Processing page {page_num} ---") 
        # Run OCR
        ocr_results = run_ocr(img, ocr_reader)
        # Find target text
        boxes = find_title_boxes(ocr_results, target_text)
        if not boxes:
            logging.warning(f"No '{target_text}' found on page {page_num}!")
            results.append({"page": page_num, "img": img, "success": False})
            continue    
        # Merge bounding boxes
        merged_box = merge_boxes(boxes)
        # Draw bounding box
        img = draw_box(img, merged_box)
        # Save image with page suffix
        page_output_path = os.path.join(output_dir, f"2-3-result_ocr_page_{page_num}.png")
        cv2.imwrite(page_output_path, img)
        logging.info(f"Saved to {page_output_path}")
        results.append({"page": page_num, "img": img, "boxes": boxes, "merged_box": merged_box, "success": True, "output_path": page_output_path})
    return results

if __name__ == "__main__":
    process_pdf("input_file/demo_cad_24.pdf", "output_file", "jib")

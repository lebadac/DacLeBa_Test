# Exercise 2

## 1. Motivation & Objectives

- **Exercise 2-3**: Utilizes Optical Character Recognition (OCR) via the `easyocr` library to scan a PDF/image, automatically detect the title region containing the keyword `"Jib"`, and highlight it with an orange bounding box.

## 2. Prerequisites
- **Conda** (Miniconda or Anaconda) installed on your system.
- **Python 3.10**
- **Poppler** (Required by `pdf2image` to convert PDF to Image):
  - **Mac:** `brew install poppler`
  - **Ubuntu:** `sudo apt-get install poppler-utils`
  - **Windows:** Download from recent releases and add `bin` to PATH.
- See `requirements.txt` for python library dependencies.

## 3. How to run

First, navigate to the `Ex2` directory in your terminal:
```bash
cd Ex2
```

### 3.1. Create and activate virtual environment
```bash
conda create -n ex2 python=3.10 -y
conda activate ex2
```

### 3.2. Install dependencies
To prevent 'Could not find import of pypdf' or similar errors, make sure you install dependencies **after** activating your environment:
```bash
pip install -r requirements.txt
```

### 3.3. Set up Input Data
Before running any script, ensure your PDF or image files are placed inside the `input_file/` directory:
```bash
mkdir input_file
# Put your demo_cad_24.pdf or other files here
```
Output results (like `2-3-result_ocr.png`) will automatically be saved into the `output_file/` directory.

### 3.4. Run the scripts
You can now run any of the exercise scripts. Make sure you are still in the `Ex2` directory:

**Run Exercise 2-3:**
```bash
python ex2_3.py
```

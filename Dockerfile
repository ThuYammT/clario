FROM odoo:17

USER root

# Install Tesseract OCR engine + language data
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-osd \
    && apt-get clean

# Install Python dependencies
RUN pip3 install pytesseract Pillow

USER odoo

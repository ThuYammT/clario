FROM odoo:17

USER root

# System libraries required by PaddleOCR
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Python OCR dependencies (CPU, stable)
RUN pip3 install --no-cache-dir \
    paddlepaddle==2.6.2 \
    paddleocr==2.9.1 \
    opencv-python-headless \
    numpy \
    Pillow

USER odoo


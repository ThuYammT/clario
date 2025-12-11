FROM odoo:17

USER root

# -------------------------------------------------------
# System dependencies (required for PaddleOCR + OpenCV)
# -------------------------------------------------------
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    libstdc++6 \
    libjpeg-dev \
    libpng-dev \
    libtiff5 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# -------------------------------------------------------
# (Optional) Tesseract OCR engine
# We keep it in case you want fallback or testing
# -------------------------------------------------------
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-osd \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# -------------------------------------------------------
# Python libraries (OCR + image processing)
# -------------------------------------------------------
RUN pip3 install --no-cache-dir \
    Pillow \
    numpy \
    opencv-python-headless

# -------------------------------------------------------
# Install PaddleOCR + PaddlePaddle (Deep Learning OCR)
# -------------------------------------------------------
# CPU version of PaddlePaddle (stable)
RUN pip3 install --no-cache-dir paddlepaddle==2.5.2 -i https://mirror.baidu.com/pypi/simple

# PaddleOCR main package (uses PaddlePaddle backend)
RUN pip3 install --no-cache-dir paddleocr

USER odoo

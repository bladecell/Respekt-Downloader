FROM datawookie/undetected-chromedriver:latest

# Copy application files
COPY ./app/ /app
WORKDIR /app

# Install ffmpeg and create required directories
RUN apt-get update && apt-get install -y ffmpeg && \
    mkdir -p /app/temp /app/data /app/downloads && \
    chmod -R 777 /app/temp && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main.py"]
FROM python:3.10-slim

# Install system tools, compiler, and dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    ffmpeg \
    fluidsynth \
    timidity \
    lilypond \
    libglib2.0-0 \
    libsmpeg0 \
    git \
    curl \
    && apt-get clean

# Install yt-dlp via pip
RUN pip install --no-cache-dir yt-dlp

# Set working directory
WORKDIR /app

# Copy project files
COPY . .


# Upgrade pip and helpers first
RUN pip install --upgrade pip setuptools wheel


# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port 
EXPOSE 8000

# Run Flask (replace backend_server.py with your main file if different)
CMD ["python", "backend_server.py"]
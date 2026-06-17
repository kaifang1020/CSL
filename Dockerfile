FROM python:3.12-slim
WORKDIR /app

# ffmpeg is needed by the audio pipeline.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pipecat's WebRTC runner. Bind all interfaces so the platform can route to it.
# On Railway set DEEPGRAM_API_KEY (so STT uses Deepgram, not local Whisper), plus
# OPENAI_API_KEY and SIMLI_API_KEY. For WebRTC behind the platform proxy you may
# also need to pass the public hostname via `--proxy <host>` (see pipecat runner).
EXPOSE 7860
CMD ["python", "patient_clinical.py", "--host", "0.0.0.0", "--port", "7860"]

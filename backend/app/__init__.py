import os as _os

# onnxruntime (Kokoro TTS) phones home to mobile.events.data.microsoft.com unless told not to. The env var must be set
# before onnxruntime is first imported anywhere in the process (render workers fork from here, so they inherit it).
_os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")

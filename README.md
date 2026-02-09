# pylumix

Python package to control a Panasonic Lumix camera over Wi-Fi (compatible with Image App capable cameras).

## Installation

Install from the local source:

```bash
pip install .
```

Or install via pipx directly from GitHub:

```bash
pipx install git+https://github.com/abichinger/pylumix
```

## Usage

```bash
# Connect to default host 192.168.54.1
pylumix info

# List files on the SD card
pylumix ls

# Download a specific file
pylumix download /DO01045134.JPG --dest image.jpg

# Preview stream to ffplay
pylumix --stdout preview | ffplay -i pipe:0 -vcodec mjpeg

# Capture image
pylumix image

# Change ISO
pylumix config iso 800
```

## Python Usage Examples

### Capture and Download Image

```python
from pylumix import LumixCamera

camera = LumixCamera("192.168.54.1")
camera.ensure_access()

print("Capturing image...")
camera.capture()

# Get the latest file info from the camera
latest = camera.get_latest_item()
print(f"Downloading {latest['title']}...")

# latest['url'] usually returns the full URL (e.g., http://.../file.jpg)
local_filename = camera.download_file(latest['url'])
print(f"Saved to {local_filename}")
```

### Start/Stop Live Preview

```python
from pylumix import LumixCamera
import cv2
import numpy as np

camera = LumixCamera("192.168.54.1")
camera.ensure_access()

print("Streaming preview... (Press 'q' to quit)")

try:
    # Stream sends UDP packets. We look for JPEG start/end markers.
    for packet in camera.stream_preview():
        start = packet.find(b'\xff\xd8')
        end = packet.find(b'\xff\xd9')
        
        if start != -1 and end != -1:
            jpeg_data = packet[start : end + 2]
            nparr = np.frombuffer(jpeg_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img is not None:
                cv2.imshow('Live Preview', img)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
finally:
    cv2.destroyAllWindows()
```

## Acknowledgements

Most of the code in this repository was written with the assistance of AI (Gemini 3 Pro).

References used:
- [libgphoto2 lumix driver](https://github.com/gphoto/libgphoto2/blob/master/camlibs/lumix/lumix.c)
- [LumixController.js](https://github.com/davidkim9/LumixController/blob/master/app/js/Lumix.js)

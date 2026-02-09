# pylumix

Python package to control a Panasonic Lumix camera over Wi-Fi.

## Installation

```bash
pip install .
```

## Usage

```bash
# Connect to default host 192.168.54.1
pylumix info

# Preview stream to ffplay
pylumix --stdout preview | ffplay -i pipe:0 -vcodec mjpeg

# Capture image
pylumix image

# Change ISO
pylumix config iso 800
```

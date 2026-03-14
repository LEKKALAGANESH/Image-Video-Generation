# backend/models/ -- Model Weights Directory

This directory should contain downloaded model weights for AuraGen's inference pipelines.

## Expected structure

```
models/
  flux/          -- FLUX Klein model weights (image generation)
  wan/           -- Wan 2.1 model weights (video generation)
  controlnet/    -- ControlNet adapter weights (structural conditioning)
  sam2/          -- SAM2 (Segment Anything 2) weights (point-to-edit segmentation)
```

## How to populate

Run `setup_models.py` from the project root to auto-download all required weights
from Hugging Face Hub:

```bash
python setup_models.py
```

The script will download each model into the appropriate subdirectory. Total disk
space required is approximately 20-30 GB depending on quantization settings.

## Important

- These directories are git-ignored (large binary files).
- Each subdirectory contains a `.gitkeep` so the folder structure is preserved in
  version control.
- Never commit model weight files (`.safetensors`, `.bin`, `.pt`) to the repository.

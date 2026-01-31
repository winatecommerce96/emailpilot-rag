
import importlib
import sys
import os

# Emulate uvicorn execution context
sys.path.insert(0, os.getcwd())

try:
    settings = importlib.import_module("pipelines.image-repository.config.settings")
    print(f"Successfully imported settings: {settings}")
    print(f"PipelineConfig: {settings.PipelineConfig}")
except ImportError as e:
    print(f"Import failed: {e}")
except Exception as e:
    print(f"Error: {e}")

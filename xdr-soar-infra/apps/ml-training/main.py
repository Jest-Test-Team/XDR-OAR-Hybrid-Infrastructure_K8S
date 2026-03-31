#!/usr/bin/env python3

import json
import os
from pathlib import Path


MODEL_NAME = os.getenv("MODEL_NAME", "risk_score")
MODEL_VERSION = os.getenv("MODEL_VERSION", "1")
MODEL_OUTPUT_DIR = Path(os.getenv("MODEL_OUTPUT_DIR", "/models"))
MONGODB_HOST = os.getenv("MONGODB_HOST", "mongodb")
SUPABASE_DB_HOST = os.getenv("SUPABASE_DB_HOST", "supabase-db")
SUPABASE_DB_PORT = os.getenv("SUPABASE_DB_PORT", "5432")


MODEL_PY = """\
import json
import numpy as np
import triton_python_backend_utils as pb_utils


class TritonPythonModel:
    def initialize(self, args):
        self.config = json.loads(args["model_config"])

    def execute(self, requests):
        responses = []
        for request in requests:
            features = pb_utils.get_input_tensor_by_name(request, "features").as_numpy()
            scores = np.mean(features, axis=1, keepdims=True).astype(np.float32)
            output = pb_utils.Tensor("risk_score", scores)
            responses.append(pb_utils.InferenceResponse(output_tensors=[output]))
        return responses
"""


def write_triton_repository(root: Path) -> None:
    model_root = root / MODEL_NAME
    version_root = model_root / MODEL_VERSION
    version_root.mkdir(parents=True, exist_ok=True)

    (model_root / "config.pbtxt").write_text(
        f"""\
name: "{MODEL_NAME}"
backend: "python"
max_batch_size: 0
input [
  {{
    name: "features"
    data_type: TYPE_FP32
    dims: [ -1 ]
  }}
]
output [
  {{
    name: "risk_score"
    data_type: TYPE_FP32
    dims: [ 1 ]
  }}
]
""",
        encoding="utf-8",
    )
    (version_root / "model.py").write_text(MODEL_PY, encoding="utf-8")

    manifest = {
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "mongodb_host": MONGODB_HOST,
        "supabase_db_host": SUPABASE_DB_HOST,
        "supabase_db_port": SUPABASE_DB_PORT,
    }
    (root / "training-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def main() -> None:
    MODEL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_triton_repository(MODEL_OUTPUT_DIR)
    print(f"Wrote Triton model repository to {MODEL_OUTPUT_DIR}", flush=True)


if __name__ == "__main__":
    main()

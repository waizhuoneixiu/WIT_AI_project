"""Explicit synthetic API for Android tests; never a fallback for cloud detection.

Run with the API virtualenv: python tests/fixture_server.py --port 8011
Records live in a temporary directory that is removed when this process exits.
"""
import argparse
import os
import sys
import tempfile
from pathlib import Path


class FixtureDetector:
    def detect(self, image, **_):
        height, width = image.shape[:2]
        return {
            "width": width,
            "height": height,
            "model": "fixture-not-yolo",
            "imgsz": 640,
            "inference_ms": 0,
            "defect_count": 1,
            "defects": [{
                "class_id": 2,
                "class_name": "patches",
                "class_cn": "斑块",
                "confidence": 0.88,
                "bbox_xyxy": [width * .2, height * .25, width * .7, height * .75],
            }],
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8011)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    with tempfile.TemporaryDirectory(prefix="steelscan-ui-fixture-") as directory:
        os.environ.update({
            "STEELSCAN_STORAGE_DIR": directory,
            "STEELSCAN_DB": str(Path(directory) / "fixture.db"),
            "STEELSCAN_API_KEY": "fixture-key",
            "DEEPSEEK_API_KEY": "",
            "LLM_PROVIDER": "deepseek",
            "MODELSCOPE_API_TOKEN": "",
        })
        import runtime
        import server
        import uvicorn

        runtime.get_detector = lambda: FixtureDetector()
        original_health = server.health

        def fixture_health():
            data = original_health()
            data.update(service="steelscan-test-fixture", model_version="fixture-not-yolo",
                        detector_provider="test-fixture", detector_configured=True)
            return data

        # Replace only the test process's health route, preserving production handlers.
        server.app.router.routes[:] = [
            route for route in server.app.router.routes if getattr(route, "path", None) != "/health"
        ]
        server.app.get("/health")(fixture_health)
        print("SYNTHETIC TEST SERVER: fixture-not-yolo; API key: fixture-key", flush=True)
        uvicorn.run(server.app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()

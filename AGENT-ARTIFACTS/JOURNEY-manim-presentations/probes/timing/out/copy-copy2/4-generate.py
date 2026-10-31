import json
from pathlib import Path

def zephon_evidence():
    return {
        "pull_requests": {
            "69": {
                "head": "b2c7adc644cdd23601c8af26005c091114459ad2",
                "diff_sha256": "e269e033adbd7b479533290ddf1f28a554b56a71079ce03170afbab65ff597f3",
                "mechanism": "freeze built hub objects before data",
            },
            "70": {
                "head": "c184603e112ae53dc27d126b375d993d93603a3a",
                "diff_sha256": "3bcfe3c1ce06ce12549f4f1457c47560a3eb4ea19c20e8fa1faf4447d7727abb",
                "mechanism": "emit int64 positions",
            },
            "71": {
                "head": "0d48b8d93af2d252edd777956fadd80b41d0e747",
                "diff_sha256": "6170e31b923b4661530b6c7cb0990b179e18896e16fd1b9a78ec3cbd86ce2ce7",
                "mechanism": "concurrent cache hits with coordinated misses",
            },
            "77": {
                "head": "9c6c458f788b79b459fa999f83c0a6afd9df0c0b",
                "diff_sha256": "fc54c7844e694790990a22208416f82cb3197d28699a998f8f4061516f58fbf0",
                "mechanism": "one v1 encode call per text",
            },
        },
        "plots": {
            "text_plus_plus": {
                "asset": "assets/zephon-text-plus-plus.png",
                "sha256": "e9430ca5740c9e37bcc086b549bc02b013a36e5f3e163e1a774f212934585c8a",
                "source_pr": 77,
                "workload": "Text++",
                "hardware": "4 × H100",
                "unit": "MTok/s",
                "rows": [
                    {
                        "id": "ceiling",
                        "label": "ready-batch ceiling",
                        "values": [5.34, 5.31],
                    },
                    {"id": "hf", "label": "HF live", "values": [2.77, 2.72]},
                    {"id": "v1", "label": "v1 live", "values": [3.19, 3.20]},
                ],
            },
            "double_stream": {
                "asset": "assets/zephon-double-stream.png",
                "sha256": "6f7d4ba16351c906976d20b953b8b6b05a86fdb7122509701f79be7b88833530",
                "source_pr": 71,
                "workload": "double stream",
                "hardware": "4 × H100",
                "unit": "MTok/s",
                "rows": [
                    {
                        "id": "ceiling",
                        "label": "ready-batch ceiling",
                        "values": [5.17, 4.95],
                    },
                    {
                        "id": "pretokenized",
                        "label": "pretokenized",
                        "values": [4.59, 4.57],
                    },
                    {
                        "id": "live_lock",
                        "label": "live with lock",
                        "values": [4.29, 4.36],
                    },
                    {
                        "id": "live_lock_free",
                        "label": "live lock-free",
                        "values": [4.98, 5.06],
                    },
                ],
            },
        },
        "gc_pause_context": {
            "workload": "single stream",
            "unit": "ms median full-GC pause",
            "before": 432,
            "after": 132,
            "source_pr": 69,
        },
    }


if __name__ == "__main__":
    path = Path(__file__).with_name("evidence.json")
    path.write_text(
        json.dumps(
            {
                "zephon": zephon_evidence(),
            },
            indent=2,
        )
        + "\n"
    )
    print(path)

"""
GGUF Exporter — safetensors → GGUF conversion + Ollama registration.

Converts MLX fine-tuned models to GGUF format for Ollama inference.
"""
import logging
import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional

_logger = logging.getLogger(__name__)

# ── Qwen2.5 ChatML template for Ollama Modelfile ──
QWEN_CHATML_TEMPLATE = """TEMPLATE \"\"\"{{- if .System }}<|im_start|>system
{{ .System }}<|im_end|>
{{- end }}<|im_start|>user
{{ .Prompt }}<|im_end|>
<|im_start|>assistant
\"\"\"
PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER top_k 20
PARAMETER repeat_penalty 1.05
"""

# ── Template registry per model family ──
_MODEL_TEMPLATES = {
    "qwen2": QWEN_CHATML_TEMPLATE,
    "qwen2.5": QWEN_CHATML_TEMPLATE,
    "qwen": QWEN_CHATML_TEMPLATE,
}


class GGUFExporter:
    """Convert safetensors model to GGUF and register with Ollama."""

    def __init__(self, llma_cpp_dir: str = ""):
        self._llama_cpp = self._resolve_llama_cpp(llma_cpp_dir)

    @staticmethod
    def _resolve_llama_cpp(custom_path: str = "") -> str:
        """Find llama.cpp installation directory."""
        search_paths = [
            custom_path,
            os.getenv("LLAMA_CPP_HOME", ""),
            str(Path.home() / "llama.cpp"),
            str(Path.home() / "workspace" / "llama.cpp"),
            "/usr/local/llama.cpp",
        ]
        for p in search_paths:
            if p and Path(p).is_dir():
                return p
        return ""

    @property
    def available(self) -> bool:
        """Check if llama.cpp tools are available."""
        if not self._llama_cpp:
            return False
        convert = Path(self._llama_cpp) / "convert_hf_to_gguf.py"
        quantize = Path(self._llama_cpp) / "llama-quantize"
        return convert.exists() and (quantize.exists() or _find_quantize(self._llama_cpp))

    def get_missing_tools(self) -> list:
        """Return list of missing tool descriptions."""
        missing = []
        if not self._llama_cpp:
            return ["llama.cpp directory not found. Set LLAMA_CPP_HOME or install to ~/llama.cpp"]
        convert = Path(self._llama_cpp) / "convert_hf_to_gguf.py"
        quantize = Path(self._llama_cpp) / "llama-quantize"
        if not convert.exists():
            missing.append(f"{convert} not found")
        if not quantize.exists() and not _find_quantize(self._llama_cpp):
            missing.append("llama-quantize not found (build llama.cpp with cmake)")
        return missing

    def fuse_adapters(self, base_model_dir: str, adapter_path: str,
                      output_dir: str) -> Optional[str]:
        """Merge LoRA adapter into base model via mlx_lm.fuse.
        
        Returns output directory path or None on failure.
        """
        try:
            import mlx_lm
        except ImportError:
            _logger.error("mlx_lm not installed — cannot fuse adapters")
            return None

        cmd = [
            "python", "-m", "mlx_lm", "fuse",
            "--model", base_model_dir,
            "--save-path", output_dir,
        ]
        if adapter_path:
            cmd.extend(["--adapter-path", adapter_path])

        _logger.info(f"Fusing adapters: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            _logger.error(f"Fuse failed: {result.stderr[:500]}")
            return None
        _logger.info(f"Fuse complete → {output_dir}")
        return output_dir

    def convert_to_gguf(self, safetensors_dir: str, output_path: str,
                        model_family: str = "qwen2", quantize: str = "Q4_K_M") -> bool:
        """Convert safetensors to GGUF with quantization.
        
        Steps:
          1. convert_hf_to_gguf.py → FP16 .gguf
          2. llama-quantize → {quantize} .gguf
        """
        if not self.available:
            _logger.error(f"llama.cpp not available: {self.get_missing_tools()}")
            return False

        # Step 1: Convert HF → GGUF (FP16)
        convert_script = str(Path(self._llama_cpp) / "convert_hf_to_gguf.py")
        fp16_path = output_path.replace(".gguf", "_fp16.gguf")
        cmd1 = [
            "python", convert_script, safetensors_dir,
            "--outfile", fp16_path,
            "--model-name", model_family,
        ]
        _logger.info(f"Convert HF→GGUF: {' '.join(cmd1)}")
        r1 = subprocess.run(cmd1, capture_output=True, text=True, timeout=600)
        if r1.returncode != 0:
            _logger.error(f"HF→GGUF failed: {r1.stderr[:500]}")
            return False

        # Step 2: Quantize
        quantize_bin = _find_quantize(self._llama_cpp)
        if not quantize_bin:
            _logger.error("llama-quantize not found")
            return False

        cmd2 = [quantize_bin, fp16_path, output_path, quantize]
        _logger.info(f"Quantize: {' '.join(cmd2)}")
        r2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=600)
        if r2.returncode != 0:
            _logger.error(f"Quantize failed: {r2.stderr[:500]}")
            return False

        # Clean up FP16 intermediate
        try:
            os.remove(fp16_path)
        except OSError:
            pass  # noqa: cleanup-best-effort

        _logger.info(f"GGUF ready → {output_path}")
        return True

    def register_ollama(self, gguf_path: str, model_name: str,
                        model_family: str = "qwen2.5") -> bool:
        """Create Ollama Modelfile and register model via `ollama create`."""
        template = _MODEL_TEMPLATES.get(model_family, QWEN_CHATML_TEMPLATE)
        modelfile_content = f"FROM {gguf_path}\n\n" + template

        # Write Modelfile
        modelfile_dir = Path(gguf_path).parent
        modelfile_path = modelfile_dir / f"Modelfile.{model_name}"
        modelfile_path.write_text(modelfile_content, encoding="utf-8")

        # Register with Ollama
        cmd = ["ollama", "create", model_name, "-f", str(modelfile_path)]
        _logger.info(f"Registering Ollama model: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            _logger.error(f"ollama create failed: {result.stderr[:500]}")
            return False

        _logger.info(f"Ollama model registered: {model_name}")
        return True


def _find_quantize(llama_cpp_dir: str) -> str:
    """Find llama-quantize binary in various locations."""
    candidates = [
        str(Path(llama_cpp_dir) / "llama-quantize"),
        str(Path(llama_cpp_dir) / "build" / "bin" / "llama-quantize"),
        str(Path(llama_cpp_dir) / "build" / "llama-quantize"),
    ]
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    # Try PATH
    found = shutil.which("llama-quantize")
    return found or ""


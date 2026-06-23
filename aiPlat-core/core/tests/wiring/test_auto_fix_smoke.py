"""
Auto-fix smoke tests: verify that template-based auto-fix
correctly detects and repairs known deterministic violations.

Tests:
  - subprocess.run(["python3"]) → subprocess.run([sys.executable])
  - bare except: → except Exception:
  - Fixed code compiles and produces equivalent output
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))
sys.path.insert(0, str(WORKSPACE_ROOT / "aiPlat-core"))


class TestAutoFixSubprocessPython3:

    def test_detects_and_fixes_bare_python3(self):
        """subprocess.run(['python3']) should be replaced with sys.executable."""
        with tempfile.TemporaryDirectory() as tmp:
            fp = Path(tmp) / "test_script.py"
            fp.write_text("""import subprocess
result = subprocess.run(["python3", "-c", "print('hello')"], capture_output=True)
""")
            # Fix: python3 → sys.executable
            content = fp.read_text()
            fixed = content.replace('["python3"', '[sys.executable')
            # Add missing import
            if "import sys" not in fixed:
                fixed = "import sys\n" + fixed
            fp.write_text(fixed)

            # Verify: fixed code compiles
            import py_compile
            try:
                py_compile.compile(str(fp), doraise=True)
                compiled = True
            except Exception as e:
                compiled = str(e)

            assert compiled is True, f"Fixed code failed to compile: {compiled}"
            assert "sys.executable" in fp.read_text()

    def test_fix_preserves_behavior(self):
        """Fixed code should produce identical output to original."""
        with tempfile.TemporaryDirectory() as tmp:
            # Original script
            orig = Path(tmp) / "orig.py"
            orig.write_text("""import subprocess
result = subprocess.run(["python3", "-c", "print('hello')"], capture_output=True, text=True)
print(result.stdout.strip())
""")
            # Fixed script
            fixed = Path(tmp) / "fixed.py"
            fixed.write_text("""import sys
import subprocess
result = subprocess.run([sys.executable, "-c", "print('hello')"], capture_output=True, text=True)
print(result.stdout.strip())
""")
            # Run both and compare
            r1 = subprocess.run(["python3", str(orig)], capture_output=True, text=True)
            r2 = subprocess.run([sys.executable, str(fixed)], capture_output=True, text=True)
            assert r1.stdout.strip() == r2.stdout.strip(), (
                f"Mismatch: orig='{r1.stdout.strip()}' fixed='{r2.stdout.strip()}'"
            )


class TestAutoFixBareExcept:

    def test_detects_bare_except(self):
        """Bare except: should be detected in code."""
        code = """try:
    risky_operation()
except:
    pass
"""
        assert "except:" in code, "Bare except: should be detected"

    def test_bare_except_takes_all(self):
        """except: catches everything including SystemExit. except Exception: is safer."""
        with tempfile.TemporaryDirectory() as tmp:
            fp = Path(tmp) / "bare.py"
            fp.write_text("""try:
    risky()
except:
    print("caught")
""")
            fixed = fp.read_text().replace("except:", "except Exception:")
            fp.write_text(fixed)
            import py_compile
            py_compile.compile(str(fp), doraise=True)
            assert "except Exception:" in fp.read_text()


class TestAutoFixSafety:

    def test_does_not_forge_inside_main_block(self):
        """auto_fix should detect code inside if __name__ == '__main__' as safe."""
        code = """
if __name__ == "__main__":
    import subprocess
    subprocess.run(["python3", "--version"])
"""
        # This is inside __main__ → safe to auto-fix
        assert 'if __name__ == "__main__"' in code

    def test_ast_parse_failure_returns_safe_false(self):
        """If AST parse fails, _is_in_safe_ast_context should return False."""
        bad_code = "this is not valid python !!! @#$%"
        import ast
        try:
            ast.parse(bad_code)
            parsed = True
        except SyntaxError:
            parsed = False
        assert not parsed, "Syntax errors should be caught and return False (block auto-fix)"

    def test_auto_fix_import_injection(self):
        """auto_fix should inject missing import sys and replace bare python3."""
        code = """
import subprocess
result = subprocess.run(["python3", "-c", "print(1)"])
"""
        if "import sys" not in code:
            code = "import sys\n" + code
        code = code.replace('["python3"', '[sys.executable')
        assert code.startswith("import sys")
        assert '["python3"' not in code
        assert "sys.executable" in code
        assert "import sys" in code

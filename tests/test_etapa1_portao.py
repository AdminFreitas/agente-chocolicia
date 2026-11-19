"""
tests/test_etapa1_portao.py — Testa o comportamento do portão AGENT_ENABLED.
Manual (CI=false): deve ignorar AGENT_ENABLED=false.
CI (CI=true): deve bloquear se AGENT_ENABLED!=true.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON_EXE = ROOT / ".venv" / "Scripts" / "python.exe"
if not PYTHON_EXE.exists():
    PYTHON_EXE = Path(sys.executable)

def test_manual_sem_ci_ignora_portao():
    env = os.environ.copy()
    env["AGENT_ENABLED"] = "false"
    env.pop("CI", None)
    
    # Chama rodar_agente.py --help para validar que passa do portão
    proc = subprocess.run(
        [str(PYTHON_EXE), str(ROOT / "rodar_agente.py"), "--help"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "Executa o agente Chocolícia" in proc.stdout

def test_ci_bloqueia_se_agent_enabled_falso():
    env = os.environ.copy()
    env["CI"] = "true"
    env["AGENT_ENABLED"] = "false"
    
    proc = subprocess.run(
        [str(PYTHON_EXE), str(ROOT / "rodar_agente.py"), "--receita", "--subcategoria", "bolos-simples"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "AGENT_ENABLED=false em ambiente CI" in proc.stdout

if __name__ == "__main__":
    test_manual_sem_ci_ignora_portao()
    print("✓ test_manual_sem_ci_ignora_portao passou")
    test_ci_bloqueia_se_agent_enabled_falso()
    print("✓ test_ci_bloqueia_se_agent_enabled_falso passou")
    print("Todos os testes da Etapa 1 passaram com sucesso!")

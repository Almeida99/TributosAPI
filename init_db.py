"""
TributosAPI - Inicialização do Banco e Ambiente
Executado automaticamente pelo entrypoint do Docker.
Aplica init.sql em todos os bancos cadastrados em data/bancos.json
(cadastro pela interface /config/bancos).
"""
import os
import sys
import subprocess

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _targets():
    """Lista de configs de banco do catálogo (interface) para aplicar o schema."""
    targets = []
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from src.core import tenants as tenants_mod

        for b in tenants_mod.list_bancos(apenas_ativos=True):
            targets.append(
                {
                    "label": b.get("slug") or b.get("nome") or "banco",
                    "server": b["server"],
                    "database": b["database"],
                    "username": b["username"],
                    "password": b["password"],
                    "driver": b.get("driver") or "ODBC Driver 18 for SQL Server",
                    "slug": b.get("slug"),
                    "nome": b.get("nome"),
                }
            )
    except Exception as e:
        print(f"   (aviso) Catálogo de bancos indisponível: {e}")

    if not targets:
        print("   (aviso) Nenhum banco no catálogo — cadastre em /config/bancos.")
    return targets


def apply_init_sql_to(cfg: dict) -> bool:
    """Executa database/init.sql no banco informado."""
    sys.path.insert(0, os.path.dirname(__file__))
    from src.core.schema_init import apply_init_sql_to_banco

    label = cfg.get("label", cfg.get("database", "?"))
    try:
        apply_init_sql_to_banco(cfg)
        print(f"   Schema aplicado com sucesso em [{label}] ({cfg.get('database')}).")
        return True
    except Exception as e:
        print(f"   (erro) [{label}] Falha ao aplicar schema: {e}")
        return False


def apply_init_sql():
    """Aplica schema em todos os bancos ativos do catálogo."""
    ok_any = False
    for cfg in _targets():
        if apply_init_sql_to(cfg):
            ok_any = True
    return ok_any


def install_packages():
    """Instala pacotes Python necessários."""
    required = ["pyodbc", "fastapi", "uvicorn", "httpx", "python-dotenv"]
    installed = []
    failed = []

    for package in required:
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", package],
                check=True,
                capture_output=True,
            )
            installed.append(package)
        except Exception:
            failed.append(package)

    return {"installed": installed, "failed": failed}


def check_packages():
    """Verifica quais pacotes estão instalados."""
    required = ["pyodbc", "fastapi", "uvicorn", "httpx", "python-dotenv"]
    status = {}

    for package in required:
        try:
            import_name = "dotenv" if package == "python-dotenv" else package.replace("-", "_")
            __import__(import_name)
            status[package] = True
        except ImportError:
            status[package] = False

    return status


if __name__ == "__main__":
    print("=" * 50)
    print("Inicializacao do TributosAPI V3 (multibanco)")
    print("=" * 50)

    print("\n1. Aplicando schema (init.sql) nos bancos do catálogo...")
    apply_init_sql()

    print("\n2. Verificando pacotes Python...")
    pkgs = check_packages()
    for pkg, ok in pkgs.items():
        status = "OK" if ok else "FALTA"
        print(f"   - {pkg}: {status}")

    if not all(pkgs.values()):
        print("\n3. Instalando pacotes faltando...")
        result = install_packages()
        print(f"   Instalados: {result['installed']}")
        if result["failed"]:
            print(f"   Falharam: {result['failed']}")

    print("\n" + "=" * 50)
    print("Inicializacao concluida!")
    print("=" * 50)

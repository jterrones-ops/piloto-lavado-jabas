import os
import sys

from supabase import create_client

TABLES = (
    "app_users", "turnos", "personal_labor", "incidencias",
    "traslados_personal", "produccion_turno", "auditoria", "configuracion",
)


def main() -> None:
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not url or not key:
        print("ERROR: faltan SUPABASE_URL o SUPABASE_SERVICE_KEY en GitHub Actions Secrets.")
        raise SystemExit(2)

    client = create_client(url, key)
    for table in TABLES:
        client.table(table).select("*").limit(1).execute()
        print(f"OK: tabla {table}")

    print("VALIDACION COMPLETA: conexión y esquema disponibles; no se insertaron datos.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR DE VALIDACION: {type(exc).__name__}: {exc}")
        sys.exit(1)

from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from supabase import create_client


OPERATIONS = {
    "Lavado de jabas": {
        "labors": ["Lavado", "Secado"],
        "shifts": [("DIA", "06:00", "18:00"), ("NOCHE", "18:00", "06:00")],
    },
    "Distribución de jabas": {
        "labors": ["Carga", "Distribución", "Recojo"],
        "shifts": [("DIA", "06:00", "14:45"), ("DIA", "15:00", "23:45"), ("NOCHE", "23:45", "06:00")],
    },
    "Luminarias": {
        "labors": ["Carga", "Distribución", "Recojo"],
        "shifts": [("DIA", "06:00", "14:45"), ("DIA", "14:00", "22:45"), ("NOCHE", "22:00", "06:45")],
    },
    "Acarreo de fruta": {
        "labors": ["Lote → Acopio", "Acopio → Packing"],
        "shifts": [("DIA", "03:00", "11:45"), ("DIA", "06:00", "14:45"), ("NOCHE", "16:00", "00:45")],
    },
    "Acopios": {
        "labors": ["Asistente (acopiador)", "Estibadores", "Montacarguistas"],
        "shifts": [("DIA", "03:00", "11:45"), ("DIA", "06:00", "14:45"), ("NOCHE", "16:00", "00:45")],
    },
}

ACOPIOS = {
    "G3-G4": (20000, "Mecanizado"), "F1-F2": (20000, "Mecanizado"),
    "F4-F5": (20000, "Mecanizado"), "E4-E5": (20000, "Mecanizado"),
    "D2-D1": (20000, "Mecanizado"), "D4-D5": (20000, "Mecanizado"),
    "B2-B3": (20000, "Mecanizado"), "G14-H14": (15000, "Manual"),
    "E14-F13": (20000, "Mecanizado"), "D15": (20000, "Mecanizado"),
    "B12": (20000, "Mecanizado"), "PK2": (20000, "Mecanizado"),
    "B7-B6": (15000, "Manual"), "C14-C15": (15000, "Manual"),
    "A13-A12": (15000, "Manual"), "D12-D13": (15000, "Manual"),
}

LIMA = ZoneInfo("America/Lima")
START_DAY = date(2026, 7, 20)
FLOWS_PER_OPERATION = 1000
EXPECTED_TURNS = len(OPERATIONS) * FLOWS_PER_OPERATION
EXPECTED_CRATES = 4_000_000
CHUNK_SIZE = 200


def chunks(rows, size=CHUNK_SIZE):
    for index in range(0, len(rows), size):
        yield rows[index:index + size]


def clock(value: str) -> time:
    return time.fromisoformat(value)


def shift_datetimes(day: date, start: str, end: str):
    started = datetime.combine(day, clock(start), tzinfo=LIMA)
    finished = datetime.combine(day, clock(end), tzinfo=LIMA)
    if finished <= started:
        finished += timedelta(days=1)
    return started, finished


def insert_rows(client, table: str, rows: list[dict]) -> None:
    for group in chunks(rows):
        client.table(table).insert(group).execute()


def active_test_users(client):
    users = client.table("app_users").select("id,rol,activo").eq("activo", True).execute().data or []
    if not users:
        raise RuntimeError("No existe ningún usuario activo para asociar la prueba.")
    assistant = next((row for row in users if str(row.get("rol", "")).upper() == "ASISTENTE"), users[0])
    supervisor = next(
        (row for row in users if str(row.get("rol", "")).upper() in ("SUPERVISOR", "JEFATURA")),
        users[0],
    )
    return str(assistant["id"]), str(supervisor["id"])


def build_operation(operation: str, assistant_id: str, supervisor_id: str, marker: str):
    config = OPERATIONS[operation]
    acopio_names = list(ACOPIOS)
    tables = {name: [] for name in ("turnos", "personal_labor", "incidencias", "traslados_personal", "produccion_turno", "auditoria", "configuracion")}

    for sequence in range(FLOWS_PER_OPERATION):
        turn_id = str(uuid4())
        day = START_DAY + timedelta(days=sequence % 90)
        shift_code, start_text, end_text = config["shifts"][sequence % len(config["shifts"])]
        started, finished = shift_datetimes(day, start_text, end_text)
        created = started.isoformat(timespec="seconds")
        operation_detail = marker
        location = None
        if operation == "Acopios":
            location = acopio_names[sequence % len(acopio_names)]
            capacity, acopio_type = ACOPIOS[location]
            operation_detail = (
                f"{marker}\nACOPIO: ubicación={location}, tipo={acopio_type}, "
                f"capacidad={capacity} jabas."
            )

        tables["turnos"].append({
            "id": turn_id, "fecha": str(day), "tipo_turno": shift_code,
            "hora_programada_inicio": start_text, "hora_programada_fin": end_text,
            "hora_real_inicio": started.isoformat(timespec="seconds"),
            "hora_real_fin": finished.isoformat(timespec="seconds"),
            "asistente_id": assistant_id, "supervisor_id": supervisor_id,
            "responsable_operacion": operation, "estado": "VALIDADO",
            "observacion_apertura": operation_detail,
            "observacion_cierre": f"{marker} · cierre automático de prueba",
            "confirmado_en": created, "cerrado_en": finished.isoformat(timespec="seconds"),
            "validado_en": finished.isoformat(timespec="seconds"),
            "creado_en": created, "actualizado_en": finished.isoformat(timespec="seconds"),
        })

        total_hours_person = 0.0
        for labor_index, labor in enumerate(config["labors"]):
            people = 1 + ((sequence + labor_index) % 20)
            effective_hours = max((finished - started).total_seconds() / 3600 - 0.75, 0)
            hours_person = round(effective_hours * people, 4)
            total_hours_person += hours_person
            tables["personal_labor"].append({
                "turno_id": turn_id, "labor": labor, "cantidad_personas": people,
                "hora_inicio": started.isoformat(timespec="seconds"),
                "hora_fin": finished.isoformat(timespec="seconds"),
                "minutos_refrigerio": 45, "horas_efectivas": round(effective_hours, 4),
                "horas_persona": hours_person, "creado_en": created,
            })

        incident_start = started + timedelta(minutes=30)
        incident_end = incident_start + timedelta(minutes=15 + sequence % 60)
        tables["incidencias"].append({
            "turno_id": turn_id, "tipo": "Otro",
            "descripcion": marker, "hora_inicio": incident_start.isoformat(timespec="seconds"),
            "hora_fin": incident_end.isoformat(timespec="seconds"),
            "duracion_minutos": int((incident_end - incident_start).total_seconds() / 60),
            "estado": "CERRADA", "registrado_por": assistant_id, "creado_en": created,
        })

        tables["traslados_personal"].append({
            "turno_id": turn_id, "hora_traslado": (started + timedelta(hours=1)).isoformat(timespec="seconds"),
            "labor_origen": config["labors"][0], "labor_destino": config["labors"][1],
            "cantidad_personas": 1, "motivo": marker,
            "registrado_por": assistant_id, "creado_en": created,
        })

        result = 4000 if operation == "Acopios" else 1000 + sequence
        tables["produccion_turno"].append({
            "turno_id": turn_id, "jabas_lavadas": result,
            "horas_persona": round(total_hours_person, 4),
            "productividad": round(result / total_hours_person, 4) if total_hours_person else 0,
            "creado_en": created, "actualizado_en": finished.isoformat(timespec="seconds"),
        })

        transitions = [
            (None, "ABIERTO", "Apertura de prueba"),
            ("ABIERTO", "CONFIRMADO", "Aprobación de prueba"),
            ("CONFIRMADO", "CERRADO", "Cierre de prueba"),
            ("CERRADO", "VALIDADO", "Validación de prueba"),
        ]
        for old, new, reason in transitions:
            tables["auditoria"].append({
                "tabla": "turnos", "registro_id": turn_id, "campo": "estado",
                "valor_anterior": "" if old is None else old, "valor_nuevo": new,
                "motivo": f"{reason} · {marker}", "usuario_id": supervisor_id,
                "creado_en": created,
            })

        if operation == "Acopios":
            departure = started + timedelta(hours=1)
            arrival = departure + timedelta(minutes=25 + sequence % 60)
            trip = {
                "numero": sequence + 1, "acopio": location,
                "tipo_acopio": ACOPIOS[location][1], "capacidad": ACOPIOS[location][0],
                "unidad": f"PRUEBA-{sequence % 200:03d}",
                "salida": departure.isoformat(timespec="seconds"),
                "llegada": arrival.isoformat(timespec="seconds"),
                "duracion_minutos": int((arrival - departure).total_seconds() / 60),
                "variedades": [
                    {"variedad": "Variedad A", "jabas": 2500},
                    {"variedad": "Variedad B", "jabas": 1500},
                ],
                "total_jabas": 4000, "estado": "FINALIZADO",
                "registrado_por": assistant_id, "lote_prueba": marker,
            }
            tables["configuracion"].append({
                "clave": f"viaje_acopio:{turn_id}:{uuid4()}",
                "valor": json.dumps(trip, ensure_ascii=False),
                "descripcion": marker, "actualizado_en": arrival.isoformat(timespec="seconds"),
            })

    return tables


def insert_operation(url: str, key: str, operation: str, assistant_id: str, supervisor_id: str, marker: str):
    client = create_client(url, key)
    tables = build_operation(operation, assistant_id, supervisor_id, marker)
    for table in ("turnos", "personal_labor", "incidencias", "traslados_personal", "produccion_turno", "auditoria", "configuracion"):
        insert_rows(client, table, tables[table])
    return operation, {table: len(rows) for table, rows in tables.items()}


def delete_by_ids(client, table: str, column: str, ids: list[str]) -> None:
    for group in chunks(ids, 100):
        client.table(table).delete().in_(column, group).execute()


def cleanup(client, marker: str) -> int:
    deleted_total = 0
    client.table("configuracion").delete().eq("descripcion", marker).execute()
    while True:
        rows = client.table("turnos").select("id").like(
            "observacion_apertura", f"%{marker}%"
        ).limit(1000).execute().data or []
        turn_ids = [str(row["id"]) for row in rows]
        if not turn_ids:
            break
        delete_by_ids(client, "auditoria", "registro_id", turn_ids)
        for table in ("produccion_turno", "traslados_personal", "incidencias", "personal_labor"):
            delete_by_ids(client, table, "turno_id", turn_ids)
        delete_by_ids(client, "turnos", "id", turn_ids)
        deleted_total += len(turn_ids)
    return deleted_total


def fetch_all(client, table: str, columns: str, filter_name: str, filter_value: str):
    rows = []
    offset = 0
    while True:
        query = client.table(table).select(columns)
        if filter_name == "like_observacion":
            query = query.like("observacion_apertura", filter_value)
        elif filter_name == "descripcion":
            query = query.eq("descripcion", filter_value)
        group = query.range(offset, offset + 999).execute().data or []
        rows.extend(group)
        if len(group) < 1000:
            return rows
        offset += 1000


def verify(client, marker: str):
    turns = fetch_all(
        client, "turnos", "id,responsable_operacion", "like_observacion", f"%{marker}%"
    )
    trip_rows = fetch_all(client, "configuracion", "clave,valor", "descripcion", marker)
    trip_rows = [row for row in trip_rows if str(row.get("clave", "")).startswith("viaje_acopio:")]
    crates = sum(int(json.loads(row["valor"]).get("total_jabas", 0)) for row in trip_rows)
    operation_counts = {
        operation: sum(1 for row in turns if row.get("responsable_operacion") == operation)
        for operation in OPERATIONS
    }
    if len(turns) != EXPECTED_TURNS:
        raise RuntimeError(f"Se esperaban {EXPECTED_TURNS} turnos y se encontraron {len(turns)}.")
    if any(count != FLOWS_PER_OPERATION for count in operation_counts.values()):
        raise RuntimeError(f"Conteo incorrecto por operación: {operation_counts}")
    if len(trip_rows) != FLOWS_PER_OPERATION or crates != EXPECTED_CRATES:
        raise RuntimeError(f"Acopios incorrectos: viajes={len(trip_rows)}, jabas={crates}.")
    return {"turnos": len(turns), "operaciones": operation_counts, "viajes": len(trip_rows), "jabas": crates}


def main() -> None:
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    batch = os.environ.get("LOAD_TEST_BATCH", "loadtest-20260720-001").strip()
    action = os.environ.get("LOAD_TEST_ACTION", "load").strip().lower()
    if not url or not key:
        raise RuntimeError("Faltan los secretos de Supabase.")
    if not batch or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for character in batch):
        raise RuntimeError("Identificador de lote inválido.")
    marker = f"PRUEBA_CARGA:{batch}"
    client = create_client(url, key)

    if action == "verify":
        summary = verify(client, marker)
        print("VERIFICACION DEL LOTE COMPLETA")
        print(f"LOTE: {batch}")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    if action == "cleanup":
        deleted = cleanup(client, marker)
        print(f"LIMPIEZA COMPLETA: lote={batch}, turnos_eliminados={deleted}")
        return
    if action != "load":
        raise RuntimeError(f"Acción desconocida: {action}")

    existing = client.table("turnos").select("id").like(
        "observacion_apertura", f"%{marker}%"
    ).execute().data or []
    if existing:
        summary = verify(client, marker)
        print("EL LOTE YA EXISTE Y FUE VALIDADO; NO SE DUPLICÓ.")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    assistant_id, supervisor_id = active_test_users(client)
    failures = []
    results = {}
    with ThreadPoolExecutor(max_workers=len(OPERATIONS)) as executor:
        futures = {
            executor.submit(insert_operation, url, key, operation, assistant_id, supervisor_id, marker): operation
            for operation in OPERATIONS
        }
        for future in as_completed(futures):
            operation = futures[future]
            try:
                completed_operation, counts = future.result()
                results[completed_operation] = counts
                print(f"OK: {completed_operation}: {counts}")
            except Exception as exc:
                failures.append(f"{operation}: {type(exc).__name__}: {exc}")

    if failures:
        deleted = cleanup(client, marker)
        raise RuntimeError(f"Carga incompleta; se revirtieron {deleted} turnos. Errores: {' | '.join(failures)}")

    try:
        summary = verify(client, marker)
        client.table("configuracion").insert({
            "clave": f"load_test_batch:{batch}",
            "valor": json.dumps(summary, ensure_ascii=False),
            "descripcion": marker,
            "actualizado_en": datetime.now(LIMA).isoformat(timespec="seconds"),
        }).execute()
    except Exception:
        deleted = cleanup(client, marker)
        raise RuntimeError(f"La validación final falló; se revirtieron {deleted} turnos.")

    print("CARGA REAL COMPLETA")
    print(f"LOTE: {batch}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("Los procesos comparten fechas y horarios para representar ejecución paralela.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        sys.exit(1)

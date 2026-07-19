from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from time import perf_counter


OPERATIONS = {
    "Lavado de jabas": {
        "labors": ["Lavado", "Secado", "Limpieza de lámina burbupack"],
        "shifts": [("Mañana", "06:00", "18:00"), ("Tarde", "18:00", "06:00")],
    },
    "Distribución de jabas": {
        "labors": ["Colocación de hilo nylon", "Colocación de lámina", "Colocación de burbupack", "Estiba", "Desestiba en puntos de cosecha"],
        "shifts": [("Mañana", "06:00", "14:45"), ("Tarde", "15:00", "23:45"), ("Noche", "23:45", "06:00")],
    },
    "Luminarias": {
        "labors": ["Carga", "Distribución", "Recojo"],
        "shifts": [("Mañana", "06:00", "14:45"), ("Tarde", "14:00", "22:45"), ("Noche", "22:00", "06:45")],
    },
    "Acarreo de fruta": {
        "labors": ["Lote → Acopio", "Acopio → Packing"],
        "shifts": [("Mañana", "03:00", "11:45"), ("Día", "06:00", "14:45"), ("Noche", "16:00", "00:45")],
    },
    "Acopios": {
        "labors": ["Asistente (acopiador)", "Estibadores", "Montacarguistas"],
        "shifts": [("Mañana", "03:00", "11:45"), ("Día", "06:00", "14:45"), ("Noche", "16:00", "00:45")],
    },
}

ACOPIOS = [
    "G3-G4", "F1-F2", "F4-F5", "E4-E5", "D2-D1", "D4-D5", "B2-B3", "G14-H14",
    "E14-F13", "D15", "B12", "PK2", "B7-B6", "C14-C15", "A13-A12", "D12-D13",
]

VALID_TRANSITIONS = {
    "ABIERTO": "CONFIRMADO",
    "CONFIRMADO": "CERRADO",
    "CERRADO": "VALIDADO",
}


def clock(value: str) -> time:
    return time.fromisoformat(value)


def shift_datetimes(day: date, start: str, end: str) -> tuple[datetime, datetime]:
    started = datetime.combine(day, clock(start))
    finished = datetime.combine(day, clock(end))
    if finished <= started:
        finished += timedelta(days=1)
    return started, finished


@dataclass
class Turn:
    operation: str
    assistant: str
    day: date
    shift: str
    scheduled_start: datetime
    scheduled_end: datetime
    acopio: str | None = None
    status: str = "ABIERTO"
    staff: dict[str, int] = field(default_factory=dict)
    incidents: list[dict] = field(default_factory=list)
    transfers: list[dict] = field(default_factory=list)
    trips: list[dict] = field(default_factory=list)
    result: int = 0


class Store:
    def __init__(self) -> None:
        self.turns: dict[tuple, Turn] = {}

    def opening_key(self, turn: Turn) -> tuple:
        base = (turn.operation, turn.assistant, turn.day, turn.scheduled_start.time())
        return base + ((turn.acopio or ""),) if turn.operation == "Acopios" else base

    def open(self, turn: Turn) -> bool:
        key = self.opening_key(turn)
        if key in self.turns:
            return False
        self.turns[key] = turn
        return True

    @staticmethod
    def transition(turn: Turn, target: str) -> None:
        expected = VALID_TRANSITIONS.get(turn.status)
        if expected != target:
            raise ValueError(f"Transición inválida: {turn.status} → {target}")
        turn.status = target


def run_flow(store: Store, operation: str, sequence: int, event_counts: Counter) -> list[str]:
    errors: list[str] = []
    config = OPERATIONS[operation]
    shift_name, start, end = config["shifts"][sequence % len(config["shifts"])]
    day = date(2026, 7, 19) + timedelta(days=sequence % 90)
    started, finished = shift_datetimes(day, start, end)
    acopio = ACOPIOS[sequence % len(ACOPIOS)] if operation == "Acopios" else None
    turn = Turn(
        operation=operation,
        assistant=f"assistant-{sequence}",
        day=day,
        shift=shift_name,
        scheduled_start=started,
        scheduled_end=finished,
        acopio=acopio,
        staff={labor: 1 + (sequence % 20) for labor in config["labors"]},
    )

    if not store.open(turn):
        errors.append("La apertura original fue rechazada")
    event_counts["apertura"] += 1

    if store.open(turn):
        errors.append("Se permitió una apertura duplicada")
    event_counts["duplicado_bloqueado"] += 1

    try:
        try:
            store.transition(turn, "CERRADO")
            errors.append("Se permitió cerrar sin aprobación del supervisor")
        except ValueError:
            event_counts["transición_inválida_bloqueada"] += 1

        store.transition(turn, "CONFIRMADO")
        event_counts["aprobación"] += 1

        incident_start = started + timedelta(minutes=30)
        incident_end = incident_start + timedelta(minutes=15 + sequence % 90)
        duration = int((incident_end - incident_start).total_seconds() / 60)
        if duration <= 0:
            errors.append("Duración de incidencia no positiva")
        turn.incidents.append({"start": incident_start, "end": incident_end, "minutes": duration})
        event_counts["incidencia_abierta"] += 1
        event_counts["incidencia_cerrada"] += 1

        if len(config["labors"]) > 1:
            origin, destination = config["labors"][:2]
            if origin == destination:
                errors.append("Traslado con origen y destino iguales")
            turn.transfers.append({"origin": origin, "destination": destination, "people": 1})
            event_counts["traslado"] += 1

        if operation == "Acopios":
            departure = started + timedelta(minutes=60)
            arrival = departure + timedelta(minutes=25 + sequence % 60)
            varieties = [{"name": "Variedad A", "crates": 2500}, {"name": "Variedad B", "crates": 1500}]
            trip = {
                "unit": f"UNIT-{sequence % 200:03d}",
                "departure": departure,
                "arrival": arrival,
                "minutes": int((arrival - departure).total_seconds() / 60),
                "varieties": varieties,
                "total_crates": sum(item["crates"] for item in varieties),
            }
            if trip["total_crates"] != 4000:
                errors.append("Total de jabas por variedad incorrecto")
            if trip["minutes"] <= 0:
                errors.append("Duración de viaje no positiva")
            turn.trips.append(trip)
            event_counts["viaje_salida"] += 1
            event_counts["viaje_llegada"] += 1

        turn.result = 1000 + sequence
        store.transition(turn, "CERRADO")
        event_counts["cierre"] += 1
        store.transition(turn, "VALIDADO")
        event_counts["validación"] += 1
    except Exception as exc:  # The report must retain the exact failing flow.
        errors.append(str(exc))

    if turn.status != "VALIDADO":
        errors.append(f"Estado final incorrecto: {turn.status}")
    if finished <= started:
        errors.append("Turno nocturno no cruza correctamente la medianoche")
    return errors


def run_operation(operation: str) -> tuple[str, Store, Counter, list[str]]:
    store = Store()
    event_counts: Counter = Counter()
    failures: list[str] = []
    for sequence in range(1000):
        errors = run_flow(store, operation, sequence, event_counts)
        failures.extend(f"Flujo {sequence + 1}: {error}" for error in errors)
    return operation, store, event_counts, failures


def main() -> None:
    started_at = perf_counter()
    with ThreadPoolExecutor(max_workers=len(OPERATIONS)) as executor:
        results = list(executor.map(run_operation, OPERATIONS))

    stores = {operation: store for operation, store, _, _ in results}
    failures = {operation: errors for operation, _, _, errors in results}
    event_counts: Counter = Counter()
    for _, _, counts, _ in results:
        event_counts.update(counts)

    elapsed = perf_counter() - started_at
    total_failures = sum(len(items) for items in failures.values())
    print("PRUEBA DE CARGA AISLADA")
    print(f"Flujos ejecutados: {len(OPERATIONS) * 1000}")
    print(f"Turnos almacenados: {sum(len(store.turns) for store in stores.values())}")
    total_crates = sum(
        trip["total_crates"]
        for turn in stores["Acopios"].turns.values()
        for trip in turn.trips
    )
    print(f"Jabas trasladadas en 90 días: {total_crates:,}")
    print(f"Eventos procesados: {sum(event_counts.values())}")
    print(f"Tiempo total: {elapsed:.4f} s")
    print(f"Errores: {total_failures}")
    print()
    for operation, errors in failures.items():
        print(f"{operation}: {1000 - len(errors)}/1000 sin errores")
        for error in errors[:10]:
            print(f"  - {error}")
    print()
    print("EVENTOS")
    for event, count in sorted(event_counts.items()):
        print(f"{event}: {count}")

    if total_crates != 4_000_000:
        raise SystemExit(f"Total de jabas incorrecto: {total_crates}")

    if total_failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
import hashlib
import hmac
import json
from time import sleep
from uuid import uuid4

import bcrypt
import pandas as pd
import streamlit as st
from supabase import create_client

st.set_page_config(
    page_title="Piloto Lavado de Jabas",
    page_icon="🧼",
    layout="wide",
    initial_sidebar_state="collapsed",
)

T = {
    "users": "app_users", "turnos": "turnos", "personal": "personal_labor",
    "inc": "incidencias", "tras": "traslados_personal",
    "prod": "produccion_turno", "audit": "auditoria", "config": "configuracion",
}
LABORES = ["Lavado", "Secado", "Limpieza de lámina burbupack"]
INCIDENCIAS = ["Falta de agua", "Falla de equipo", "Falta de energía", "Falta de jabas",
               "Falta de personal", "Limpieza del área", "Desperfecto mecánico",
               "Acumulación de jabas", "Otro"]
OPERACIONES = [
    {
        "icon": "", "name": "Lavado de jabas", "enabled": True,
        "responsables": ["Asistente · Rafael Zapata"],
        "labores": ["Lavado", "Secado", "Limpieza de lámina burbupack"],
    },
    {
        "icon": "📦", "name": "Distribución de jabas", "enabled": True,
        "responsables": ["Supervisor · Luis Macea"],
        "labores": ["Colocación de hilo nylon", "Colocación de lámina", "Colocación de burbupack",
                    "Estiba", "Desestiba en puntos de cosecha"],
    },
    {
        "icon": "💡", "name": "Luminarias", "enabled": True,
        "responsables": ["Supervisor · Por definir"],
        "labores": ["Carga", "Distribución", "Recojo"],
    },
    {
        "icon": "🚜", "name": "Acarreo de fruta", "enabled": True,
        "responsables": ["Supervisor · Enisban Calle", "Supervisor · Juan Cruz"],
        "labores": ["Lote → Acopio", "Acopio → Packing"],
    },
    {
        "icon": "🏭", "name": "Acopios", "enabled": True,
        "responsables": ["Supervisor · Andrés Villegas"],
        "labores": ["Asistente (acopiador)", "Estibadores", "Montacarguistas"],
    },
]
SHIFT_SCHEDULES = {
    "Lavado de jabas": [
        {"label": "Mañana", "code": "DIA", "start": "06:00", "end": "18:00"},
        {"label": "Tarde", "code": "NOCHE", "start": "18:00", "end": "06:00"},
    ],
    "Distribución de jabas": [
        {"label": "Mañana", "code": "DIA", "start": "06:00", "end": "14:45"},
        {"label": "Tarde", "code": "DIA", "start": "15:00", "end": "23:45"},
        {"label": "Noche", "code": "NOCHE", "start": "23:45", "end": "06:00"},
    ],
    "Luminarias": [
        {"label": "Mañana", "code": "DIA", "start": "06:00", "end": "14:45"},
        {"label": "Tarde", "code": "DIA", "start": "14:00", "end": "22:45"},
        {"label": "Noche", "code": "NOCHE", "start": "22:00", "end": "06:45"},
    ],
    "Acarreo de fruta": [
        {"label": "Mañana", "code": "DIA", "start": "03:00", "end": "11:45"},
        {"label": "Día", "code": "DIA", "start": "06:00", "end": "14:45"},
        {"label": "Noche", "code": "NOCHE", "start": "16:00", "end": "00:45"},
    ],
    "Acopios": [
        {"label": "Mañana", "code": "DIA", "start": "03:00", "end": "11:45"},
        {"label": "Día", "code": "DIA", "start": "06:00", "end": "14:45"},
        {"label": "Noche", "code": "NOCHE", "start": "16:00", "end": "00:45"},
    ],
}
ACOPIOS = {
    "G3-G4": {"capacidad": 20000, "tipo": "Mecanizado"},
    "F1-F2": {"capacidad": 20000, "tipo": "Mecanizado"},
    "F4-F5": {"capacidad": 20000, "tipo": "Mecanizado"},
    "E4-E5": {"capacidad": 20000, "tipo": "Mecanizado"},
    "D2-D1": {"capacidad": 20000, "tipo": "Mecanizado"},
    "D4-D5": {"capacidad": 20000, "tipo": "Mecanizado"},
    "B2-B3": {"capacidad": 20000, "tipo": "Mecanizado"},
    "G14-H14": {"capacidad": 15000, "tipo": "Manual"},
    "E14-F13": {"capacidad": 20000, "tipo": "Mecanizado"},
    "D15": {"capacidad": 20000, "tipo": "Mecanizado"},
    "B12": {"capacidad": 20000, "tipo": "Mecanizado"},
    "PK2": {"capacidad": 20000, "tipo": "Mecanizado"},
    "B7-B6": {"capacidad": 15000, "tipo": "Manual"},
    "C14-C15": {"capacidad": 15000, "tipo": "Manual"},
    "A13-A12": {"capacidad": 15000, "tipo": "Manual"},
    "D12-D13": {"capacidad": 15000, "tipo": "Manual"},
}
ALL_OPERATIONS = "Todas las operaciones"
LIMA = ZoneInfo("America/Lima")


@st.cache_resource
def db():
    url = st.secrets.get("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("Faltan los Secrets de Supabase.")
    return create_client(url, key)


try:
    sb = db()
except Exception as e:
    st.error(f"No se pudo conectar con Supabase: {e}")
    st.stop()


def now():
    return datetime.now(LIMA).isoformat(timespec="seconds")


def timestamp(day, clock):
    return datetime.combine(day, clock, tzinfo=LIMA).isoformat(timespec="seconds")


def get(table, filters=None, order="creado_en"):
    for attempt in range(3):
        try:
            query = sb.table(table).select("*")
            for key, value in (filters or {}).items():
                query = query.eq(key, value)
            if order:
                query = query.order(order, desc=True)
            return query.execute().data or []
        except Exception:
            if attempt < 2:
                sleep(0.6 * (attempt + 1))
    st.error("No se pudo consultar la información en este momento.")
    st.info("Espera unos segundos y presiona Reintentar. Los registros guardados no se han eliminado.")
    if st.button("Reintentar conexión", use_container_width=True, key=f"retry_{table}"):
        st.rerun()
    st.stop()


def frame(table, filters=None, order="creado_en"):
    return pd.DataFrame(get(table, filters, order))


def paged_frame(table, filters=None, order="creado_en", page_size=1000):
    rows = []
    offset = 0
    while True:
        try:
            query = sb.table(table).select("*")
            for key, value in (filters or {}).items():
                query = query.eq(key, value)
            if order:
                query = query.order(order, desc=True)
            batch = query.range(offset, offset + page_size - 1).execute().data or []
        except Exception:
            st.error("No se pudo consultar la información completa del Dashboard.")
            st.stop()
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return pd.DataFrame(rows)


def frame_for_turn_ids(table, turn_ids, chunk_size=100):
    ids = list({str(turn_id) for turn_id in turn_ids})
    rows = []
    for offset in range(0, len(ids), chunk_size):
        try:
            batch = (
                sb.table(table).select("*")
                .in_("turno_id", ids[offset:offset + chunk_size])
                .execute().data or []
            )
        except Exception:
            st.error("No se pudo completar el resumen operativo del Dashboard.")
            st.stop()
        rows.extend(batch)
    return pd.DataFrame(rows)


def add(table, data):
    try:
        rows = sb.table(table).insert(data).execute().data or []
        return rows[0] if rows else None
    except Exception:
        st.error("No se pudo confirmar el registro.")
        st.info("Verifica si el registro aparece antes de volver a enviarlo, para evitar duplicados.")
        st.stop()


def edit(table, data, filters):
    try:
        query = sb.table(table).update(data)
        for key, value in filters.items():
            query = query.eq(key, value)
        return query.execute().data or []
    except Exception:
        st.error("No se pudo confirmar la actualización.")
        st.info("El sistema no continuará hasta recuperar la conexión. Intenta nuevamente en unos segundos.")
        st.stop()


def acopio_trips(turn_id):
    prefix = f"viaje_acopio:{turn_id}:"
    trips = []
    for row in get(T["config"], order=None):
        key = str(row.get("clave", ""))
        if not key.startswith(prefix):
            continue
        try:
            trip = json.loads(row.get("valor") or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        trip["_key"] = key
        trips.append(trip)
    return sorted(trips, key=lambda item: item.get("salida", ""), reverse=True)


def acopio_entries(turn_id):
    prefix = f"ingreso_acopio:{turn_id}:"
    entries = []
    try:
        rows = sb.table(T["config"]).select("clave,valor").like("clave", f"{prefix}%").execute().data or []
    except Exception:
        st.error("No se pudieron consultar las recepciones del acopio.")
        st.stop()
    for row in rows:
        try:
            entry = json.loads(row.get("valor") or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        entry["_key"] = row.get("clave")
        entries.append(entry)
    return sorted(entries, key=lambda item: item.get("hora", ""), reverse=True)


def save_acopio_entry(turn_id, entry):
    key = f"ingreso_acopio:{turn_id}:{uuid4()}"
    add(T["config"], {
        "clave": key,
        "valor": json.dumps(entry, ensure_ascii=False),
        "descripcion": "Recepción de jabas en punto de acopio",
        "actualizado_en": now(),
    })
    return key


def save_acopio_trip(turn_id, trip):
    key = f"viaje_acopio:{turn_id}:{uuid4()}"
    add(T["config"], {
        "clave": key,
        "valor": json.dumps(trip, ensure_ascii=False),
        "descripcion": "Registro piloto de viaje desde punto de acopio",
        "actualizado_en": now(),
    })
    return key


def update_acopio_trip(key, trip):
    edit(T["config"], {
        "valor": json.dumps(trip, ensure_ascii=False),
        "actualizado_en": now(),
    }, {"clave": key})


def turn_acopio(turn_id):
    turns = frame(T["turnos"], {"id": turn_id})
    if turns.empty:
        return None
    observation = str(turns.iloc[0].get("observacion_apertura") or "")
    marker = "ACOPIO: ubicación="
    if marker not in observation:
        return None
    location = observation.split(marker, 1)[1].split(",", 1)[0].strip()
    return location if location in ACOPIOS else None


def assigned_operation(account_id):
    rows = get(T["config"], {"clave": f"operacion_usuario:{account_id}"}, order=None)
    return rows[0]["valor"] if rows else "Lavado de jabas"


def has_global_operation_access(account_id):
    rows = get(T["config"], {"clave": f"acceso_global_operaciones:{account_id}"}, order=None)
    return bool(rows) and str(rows[0].get("valor", "")).strip().lower() == "true"


def save_assigned_operation(account_id, operation):
    sb.table(T["config"]).upsert({
        "clave": f"operacion_usuario:{account_id}",
        "valor": operation,
        "descripcion": "Operación principal asignada al usuario",
        "actualizado_en": now(),
    }, on_conflict="clave").execute()


def daily_plan_key(plan_date):
    return f"plan_diario:{plan_date}"


def load_daily_plan(plan_date):
    rows = get(T["config"], {"clave": daily_plan_key(plan_date)}, order=None)
    if not rows:
        return {"jabas_recibidas": 0, "jabas_packing": 0, "procesos": {}}
    try:
        plan = json.loads(rows[0].get("valor") or "{}")
    except (TypeError, json.JSONDecodeError):
        plan = {}
    plan.setdefault("jabas_recibidas", 0)
    plan.setdefault("jabas_packing", 0)
    plan.setdefault("procesos", {})
    return plan


def save_daily_plan(plan_date, plan):
    sb.table(T["config"]).upsert({
        "clave": daily_plan_key(plan_date),
        "valor": json.dumps(plan, ensure_ascii=False),
        "descripcion": "Planificación diaria consolidada de Jefatura",
        "actualizado_en": now(),
    }, on_conflict="clave").execute()


def acopio_trip_totals(turn_ids):
    turn_ids = {str(turn_id) for turn_id in turn_ids}
    total_jabas = 0
    total_trips = 0
    if not turn_ids:
        return total_jabas, total_trips
    offset = 0
    while True:
        try:
            rows = (
                sb.table(T["config"]).select("clave,valor")
                .like("clave", "viaje_acopio:%")
                .range(offset, offset + 999).execute().data or []
            )
        except Exception:
            st.error("No se pudo completar el total de viajes a packing.")
            st.stop()
        for row in rows:
            key = str(row.get("clave", ""))
            parts = key.split(":", 2)
            if len(parts) < 3 or parts[1] not in turn_ids:
                continue
            try:
                trip = json.loads(row.get("valor") or "{}")
            except (TypeError, json.JSONDecodeError):
                continue
            total_trips += 1
            total_jabas += int(trip.get("total_jabas", 0) or 0)
        if len(rows) < 1000:
            break
        offset += 1000
    return total_jabas, total_trips


def acopio_entry_totals(turn_ids):
    turn_ids = {str(turn_id) for turn_id in turn_ids}
    total_jabas = 0
    total_entries = 0
    if not turn_ids:
        return total_jabas, total_entries
    offset = 0
    while True:
        try:
            rows = (
                sb.table(T["config"]).select("clave,valor")
                .like("clave", "ingreso_acopio:%")
                .range(offset, offset + 999).execute().data or []
            )
        except Exception:
            st.error("No se pudo completar el total de jabas recibidas en acopios.")
            st.stop()
        for row in rows:
            parts = str(row.get("clave", "")).split(":", 2)
            if len(parts) < 3 or parts[1] not in turn_ids:
                continue
            try:
                entry = json.loads(row.get("valor") or "{}")
            except (TypeError, json.JSONDecodeError):
                continue
            total_entries += 1
            total_jabas += int(entry.get("total_jabas", 0) or 0)
        if len(rows) < 1000:
            break
        offset += 1000
    return total_jabas, total_entries


def production_total(turn_ids):
    total = 0
    for turn_id in {str(turn_id) for turn_id in turn_ids}:
        production = frame(T["prod"], {"turno_id": turn_id})
        if not production.empty and "jabas_lavadas" in production:
            total += int(pd.to_numeric(
                production["jabas_lavadas"], errors="coerce"
            ).fillna(0).sum())
    return total


def personnel_total(turn_ids):
    total = 0
    for turn_id in {str(turn_id) for turn_id in turn_ids}:
        personal = frame(T["personal"], {"turno_id": turn_id})
        if not personal.empty and "cantidad_personas" in personal:
            total += int(pd.to_numeric(
                personal["cantidad_personas"], errors="coerce"
            ).fillna(0).sum())
    return total


def plan_status(operation_data, planned_people, actual_people, incident_count=0):
    if planned_people <= 0:
        return "Sin planificación", "off"
    if operation_data.empty:
        return "Fuera de lo planificado", "red"
    coverage = actual_people / planned_people if planned_people else 0
    waiting = int((operation_data["estado"] == "ABIERTO").sum())
    if coverage >= 1 and waiting == 0 and incident_count == 0:
        return "Dentro de lo planificado", "green"
    if coverage >= 0.9 and incident_count == 0:
        return "En riesgo", "orange"
    return "Fuera de lo planificado", "red"


def render_management_quick_navigation():
    spacer, planning, reports, administration = st.columns([5, 1.4, 1.2, 1.5])
    with planning:
        if st.button("Planificación", use_container_width=True, key="management_nav_planning"):
            st.session_state["current_section_JEFATURA"] = "Planificación"
            st.rerun()
    with reports:
        if st.button("Reportes", use_container_width=True, key="management_nav_reports"):
            st.session_state["current_section_JEFATURA"] = "Reportes"
            st.rerun()
    with administration:
        if st.button("Administración", use_container_width=True, key="management_nav_admin"):
            st.session_state["current_section_JEFATURA"] = "Administración"
            st.rerun()


def render_management_budget_demo():
    """Full consolidated Jefatura preview using fictitious, non-persistent values."""
    st.markdown("""
    <style>
    .demo-note {
        padding: .75rem 1rem; border-radius: .7rem; margin: .4rem 0 1.1rem;
        color: #075985; background: #e0f2fe; border: 1px solid #bae6fd;
        font-size: .92rem;
    }
    .dashboard-section-title {
        color: #13233d; font-size: 1.35rem; font-weight: 750;
        margin: 1.35rem 0 .7rem;
    }
    .kpi-grid {
        display: grid; grid-template-columns: repeat(5, minmax(0, 1fr));
        gap: .85rem; margin-bottom: 1.35rem;
    }
    .kpi-card {
        background: #ffffff; border: 1px solid #dbe3ee; border-radius: .85rem;
        padding: 1rem 1.05rem; box-shadow: 0 2px 7px rgba(15, 35, 65, .05);
    }
    .kpi-label {color: #536176; font-size: .87rem; margin-bottom: .3rem;}
    .kpi-value {color: #10213d; font-size: 2rem; font-weight: 780; line-height: 1.05;}
    .kpi-danger .kpi-value {color: #dc2626;}
    .operation-card {
        min-height: 19rem; background: #fff; border: 1px solid #dbe3ee;
        border-radius: .85rem; padding: .9rem .95rem .7rem;
        box-shadow: 0 2px 7px rgba(15, 35, 65, .045);
    }
    .operation-title {
        color: #13233d; font-size: 1.02rem; font-weight: 750;
        min-height: 2.6rem; margin-bottom: .45rem;
    }
    .status-pill {
        display: inline-block; padding: .22rem .62rem; border-radius: .45rem;
        font-size: .78rem; font-weight: 650; margin-bottom: .65rem;
    }
    .status-green {color: #166534; background: #dcfce7; border: 1px solid #86efac;}
    .status-orange {color: #9a5a00; background: #fff7d6; border: 1px solid #f5c451;}
    .status-blue {color: #0755a5; background: #e7f2ff; border: 1px solid #93c5fd;}
    .metric-row {
        display: flex; justify-content: space-between; gap: .65rem;
        padding: .47rem 0; border-bottom: 1px solid #edf1f6;
        color: #526075; font-size: .85rem;
    }
    .metric-row strong {color: #15243d; font-size: .9rem;}
    .budget-table-wrap {
        overflow-x: auto; background: white; border: 1px solid #dbe3ee;
        border-radius: .8rem; margin-top: .3rem;
    }
    .budget-table {border-collapse: collapse; width: 100%; min-width: 760px;}
    .budget-table th {
        text-align: left; color: #26364f; background: #f4f7fb;
        padding: .7rem .8rem; font-size: .84rem; border-bottom: 1px solid #dbe3ee;
    }
    .budget-table td {
        color: #26364f; padding: .65rem .8rem; font-size: .84rem;
        border-bottom: 1px solid #edf1f6;
    }
    .difference-up {color: #dc2626 !important; font-weight: 700;}
    .difference-down {color: #15803d !important; font-weight: 700;}
    @media (max-width: 1100px) {
        .kpi-grid {grid-template-columns: repeat(2, minmax(0, 1fr));}
        .operation-card {min-height: auto;}
    }
    .block-container {max-width: 1800px; padding-top: 2.2rem;}
    </style>
    <div class="demo-note"><strong>Dashboard consolidado v3</strong> · Vista ficticia dinámica ·
    Solo visible para Jefatura · No guarda datos</div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="dashboard-section-title">Resumen general del día</div>',
                unsafe_allow_html=True)
    headline_values = [
        ("Jabas recibidas", "92,500"),
        ("Jabas a packing", "61,200"),
        ("Jabas lavadas", "42,500"),
        ("Personal del día", "128"),
        ("Incidencias abiertas", "3"),
    ]
    headline_html = "".join(
        f'<div class="kpi-card {"kpi-danger" if label == "Incidencias abiertas" else ""}">'
        f'<div class="kpi-label">{label}</div><div class="kpi-value">{value}</div></div>'
        for label, value in headline_values
    )
    st.markdown(f'<div class="kpi-grid">{headline_html}</div>', unsafe_allow_html=True)

    st.markdown('<div class="dashboard-section-title">Estado de las operaciones</div>',
                unsafe_allow_html=True)
    operation_cards = [
        {
            "name": "Lavado de jabas", "status": "En riesgo", "color": "orange",
            "metrics": [("Plan", "45,000"), ("Real", "42,500"),
                        ("Cumplimiento", "94.4%"), ("Personal", "44")],
        },
        {
            "name": "Distribución de jabas", "status": "Dentro del plan", "color": "green",
            "metrics": [("Jabas distribuidas", "78,400"), ("Personal", "26"), ("Turnos", "3")],
        },
        {
            "name": "Luminarias", "status": "Dentro del plan", "color": "green",
            "metrics": [("Entregadas", "320"), ("Recibidas", "305"),
                        ("Mal estado", "6"), ("Personal", "18")],
        },
        {
            "name": "Acarreo de fruta", "status": "En ejecución", "color": "blue",
            "metrics": [("Viajes", "48"), ("Tractores", "7"),
                        ("Motofurgones", "3"), ("Personal", "21")],
        },
        {
            "name": "Acopios", "status": "En ejecución", "color": "blue",
            "metrics": [("Recepciones", "36"), ("Viajes a packing", "22"),
                        ("Stock", "31,300"), ("Personal", "19")],
        },
    ]
    report_columns = st.columns(5)
    for column, card in zip(report_columns, operation_cards):
        rows_html = "".join(
            f'<div class="metric-row"><span>{label}</span><strong>{value}</strong></div>'
            for label, value in card["metrics"]
        )
        with column:
            st.markdown(
                f'<div class="operation-card"><div class="operation-title">{card["name"]}</div>'
                f'<span class="status-pill status-{card["color"]}">{card["status"]}</span>'
                f'{rows_html}</div>',
                unsafe_allow_html=True,
            )
            if st.button(
                "Ver reporte", key=f"demo_report_{card['name']}", use_container_width=True
            ):
                st.session_state["management_report_operation"] = card["name"]
                st.session_state["current_section_JEFATURA"] = "Reportes"
                st.rerun()

    st.markdown(
        '<div class="dashboard-section-title">Resumen presupuesto vs. real · Solo Jefatura</div>',
        unsafe_allow_html=True,
    )
    comparison = [
        ("Lavado de jabas", "US$1,111.74", "US$1,164.68", "+US$52.94", "Desviación", "up"),
        ("Distribución de jabas", "US$832.50", "US$815.20", "-US$17.30", "Dentro del plan", "down"),
        ("Luminarias", "US$642.80", "US$636.10", "-US$6.70", "Dentro del plan", "down"),
        ("Acarreo de fruta", "US$1,255.60", "US$1,228.45", "-US$27.15", "Dentro del plan", "down"),
        ("Acopios", "US$903.40", "US$915.85", "+US$12.45", "Desviación", "up"),
    ]
    table_rows = "".join(
        f'<tr><td>{process}</td><td>{plan}</td><td>{actual}</td>'
        f'<td class="difference-{direction}">{difference}</td><td>{status}</td></tr>'
        for process, plan, actual, difference, status, direction in comparison
    )
    st.markdown(
        '<div class="budget-table-wrap"><table class="budget-table">'
        '<thead><tr><th>Proceso</th><th>Plan</th><th>Real</th><th>Diferencia</th>'
        f'<th>Estado</th></tr></thead><tbody>{table_rows}</tbody></table></div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Montos expresados en dólares estadounidenses (USD). En Lavado se aplican 40% "
        "de jabas blancas, 10% de rojas y US$26.47 por persona/jornada."
    )


def audit(table, record_id, field, old, new, reason, user_id):
    add(T["audit"], {
        "tabla": table, "registro_id": record_id, "campo": field,
        "valor_anterior": "" if old is None else str(old),
        "valor_nuevo": "" if new is None else str(new),
        "motivo": reason, "usuario_id": user_id, "creado_en": now(),
    })


def minutes_between(start, end):
    return max(int((end - start).total_seconds() / 60), 0)


def password_is_valid(password, stored_hash):
    stored_hash = str(stored_hash or "").strip()
    if not password or not stored_hash:
        return False
    try:
        if stored_hash.startswith(("$2a$", "$2b$", "$2y$")):
            return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
        if len(stored_hash) == 64:
            calculated = hashlib.sha256(password.encode("utf-8")).hexdigest()
            return hmac.compare_digest(calculated.lower(), stored_hash.lower())
    except (ValueError, TypeError):
        return False
    return False


def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


all_users = frame(T["users"], order="nombre")
users = all_users.copy()
if not users.empty and "activo" in users:
    users = users[users["activo"].fillna(False).astype(bool)]
user_by_id = {str(row["id"]): row["nombre"] for _, row in users.iterrows()} if not users.empty else {}

if not st.session_state.get("authenticated"):
    st.markdown("""
    <style>
    [data-testid="stSidebar"] {display: none;}
    .block-container {max-width: 560px; padding-top: 4rem;}
    </style>
    """, unsafe_allow_html=True)
    st.title("Control de Operaciones Logísticas")
    st.subheader("Ingreso al sistema")
    st.caption("Identifícate para consultar las operaciones disponibles.")
    with st.form("login"):
        login_user = st.text_input(
            "Usuario o nombre",
            placeholder="Ejemplo: asistente.piloto o Asistente Piloto",
        )
        login_password = st.text_input("Contraseña", type="password", placeholder="Escribe tu contraseña")
        login_button = st.form_submit_button("INGRESAR", type="primary", use_container_width=True)
        if login_button:
            entered_identity = login_user.strip().lower()
            matches = users[
                (users["usuario"].astype(str).str.lower() == entered_identity)
                | (users["nombre"].astype(str).str.lower() == entered_identity)
            ] if not users.empty else pd.DataFrame()
            account = None
            for _, candidate in matches.iterrows():
                if password_is_valid(login_password, candidate["clave_hash"]):
                    account = candidate
                    break
            if account is None:
                st.error("Usuario o contraseña incorrectos.")
            else:
                st.session_state["authenticated"] = True
                st.session_state["user_id"] = str(account["id"])
                st.rerun()
    st.stop()

current = users[users["id"].astype(str) == str(st.session_state.get("user_id"))]
if current.empty:
    st.session_state.clear()
    st.warning("Tu acceso ya no está activo. Vuelve a ingresar.")
    st.rerun()

user_row = current.iloc[0]
user_id = str(user_row["id"])
user_name = str(user_row["nombre"])
role = str(user_row["rol"]).upper()
account_role = role
user_operation = assigned_operation(user_id)
global_operation_access = has_global_operation_access(user_id)
if account_role == "JEFATURA":
    st.session_state["selected_operation"] = ALL_OPERATIONS

st.sidebar.title("Operaciones Logísticas")
st.sidebar.write(f"**{user_name}**")
st.sidebar.caption(role.title())
if st.sidebar.button("Cerrar sesión", use_container_width=True):
    st.session_state.clear()
    st.rerun()

if account_role == "ASISTENTE" and st.session_state.get("assistant_entry_module"):
    if st.sidebar.button("Volver al inicio", use_container_width=True):
        st.session_state.pop("assistant_entry_module", None)
        st.session_state.pop("main_navigation_ASISTENTE", None)
        if global_operation_access:
            st.session_state.pop("selected_operation", None)
        st.rerun()

if account_role == "ASISTENTE" and not st.session_state.get("assistant_entry_module"):
    st.title("Inicio")
    st.caption("Selecciona el módulo al que deseas ingresar.")
    modules = [
        ("Planificación", "Consulta lo programado para la jornada."),
        ("Operaciones", "Ingresa y registra la ejecución del turno."),
        ("Reportes", "Revisa resultados e incidencias."),
    ]
    for column, (module, description) in zip(st.columns(3), modules):
        with column.container(border=True):
            st.subheader(module)
            st.caption(description)
            if st.button(
                "Ingresar", key=f"enter_module_{module}",
                type="primary", use_container_width=True,
            ):
                st.session_state["assistant_entry_module"] = module
                st.session_state["main_navigation_ASISTENTE"] = module
                if global_operation_access:
                    if module == "Operaciones":
                        st.session_state.pop("selected_operation", None)
                    elif not st.session_state.get("selected_operation"):
                        st.session_state["selected_operation"] = user_operation
                st.rerun()
    st.stop()

if role in ("ASISTENTE", "SUPERVISOR") and not global_operation_access:
    st.session_state["selected_operation"] = user_operation

if not st.session_state.get("selected_operation"):
    st.title("Operaciones")
    st.caption("Selecciona la operación que deseas revisar.")
    available_operations = [operation for operation in OPERACIONES if operation["enabled"]]
    columns = st.columns(3)
    for index, operation in enumerate(available_operations):
        name = operation["name"]
        icon = operation["icon"]
        with columns[index % 3]:
            if st.button(
                f"{icon} {name}", key=f"select_operation_{index}",
                use_container_width=True, type="primary",
            ):
                st.session_state["selected_operation"] = name
                st.rerun()
    st.stop()

if account_role == "JEFATURA":
    st.sidebar.caption("Vista: Todas las operaciones")
else:
    st.sidebar.caption(f"Operación: {st.session_state['selected_operation']}")
if global_operation_access and st.sidebar.button(
    "Cambiar operación", use_container_width=True
):
    st.session_state.pop("selected_operation", None)
    st.rerun()

selected_operation = st.session_state["selected_operation"]
operation_config = next(
    (operation for operation in OPERACIONES if operation["name"] == selected_operation),
    None,
)
LABORES = operation_config["labores"] if operation_config else []

sections = {
    "ASISTENTE": ["Planificación", "Operaciones", "Reportes"],
    "SUPERVISOR": ["Dashboard", "Operaciones", "Reportes"],
    "JEFATURA": ["Dashboard", "Planificación", "Reportes", "Administración"],
}
if role not in sections:
    st.error("El rol de este usuario no está configurado correctamente.")
    st.stop()

navigation_key = f"current_section_{role}"
if role == "ASISTENTE":
    section = st.session_state.get("assistant_entry_module", "Planificación")
else:
    if st.session_state.get(navigation_key) not in sections[role]:
        st.session_state[navigation_key] = "Dashboard"
    section = st.session_state[navigation_key]
    if section != "Dashboard":
        if st.sidebar.button("Volver al Dashboard", use_container_width=True):
            st.session_state[navigation_key] = "Dashboard"
            st.rerun()

page = section
if role == "ASISTENTE" and section == "Operaciones":
    assistant_active_data = frame(T["turnos"], {"asistente_id": user_id})
    if not assistant_active_data.empty and "responsable_operacion" in assistant_active_data:
        operation_names = [operation["name"] for operation in OPERACIONES]
        operation_values = assistant_active_data["responsable_operacion"].fillna("").astype(str)
        if selected_operation == "Lavado de jabas":
            assistant_active_data = assistant_active_data[
                (operation_values == selected_operation) | (~operation_values.isin(operation_names))
            ]
        else:
            assistant_active_data = assistant_active_data[operation_values == selected_operation]
    if not assistant_active_data.empty:
        assistant_active_data = assistant_active_data[
            assistant_active_data["estado"].isin(["ABIERTO", "CONFIRMADO", "CERRADO"])
        ]
    close_mode_key = f"assistant_close_mode_{user_id}_{selected_operation}"
    if not assistant_active_data.empty and (assistant_active_data["estado"] == "CONFIRMADO").any():
        page = "Cerrar turno" if st.session_state.get(close_mode_key) else "Operación"
    elif not assistant_active_data.empty and (assistant_active_data["estado"] == "ABIERTO").any():
        page = "Abrir turno"
    elif not assistant_active_data.empty and (assistant_active_data["estado"] == "CERRADO").any():
        page = "Cerrar turno"
    else:
        page = "Abrir turno"
elif role == "SUPERVISOR":
    if section == "Dashboard":
        page = "Panel"
    elif section == "Operaciones":
        page = st.radio(
            "Acción", ["Confirmar apertura", "Seguimiento", "Validar cierre"],
            horizontal=True, key="supervisor_operation_action",
        )
elif role == "JEFATURA":
    page = {
        "Dashboard": "Panel",
        "Planificación": "Planificación",
        "Reportes": "Reportes",
        "Administración": "Usuarios y accesos",
    }[section]


def turn_label(row):
    assistant = user_by_id.get(str(row["asistente_id"]), "Sin asignar")
    shift = shift_label_for_row(row)
    status = STATUS_LABELS.get(row["estado"], row["estado"])
    context = turn_acopio(str(row["id"])) if selected_operation == "Acopios" else selected_operation
    return f"{context or selected_operation} | {row['fecha']} | {shift} | {assistant} | {status}"


def filter_current_operation(data):
    if selected_operation == ALL_OPERATIONS:
        return data
    if data.empty or "responsable_operacion" not in data:
        return data
    operation_names = [operation["name"] for operation in OPERACIONES]
    values = data["responsable_operacion"].fillna("").astype(str)
    if selected_operation == "Lavado de jabas":
        return data[(values == selected_operation) | (~values.isin(operation_names))]
    return data[values == selected_operation]


STATUS_LABELS = {
    "ABIERTO": "Esperando supervisor",
    "CONFIRMADO": "En ejecución",
    "CERRADO": "Cierre pendiente",
    "VALIDADO": "Finalizado",
}

RESULT_LABELS = {
    "Lavado de jabas": "Jabas lavadas",
    "Distribución de jabas": "Jabas distribuidas",
    "Luminarias": "Luminarias gestionadas",
    "Acarreo de fruta": "Movimientos realizados",
    "Acopios": "Jabas atendidas",
}


def shift_label_for_row(row):
    start = str(row.get("hora_programada_inicio", ""))[:5]
    end = str(row.get("hora_programada_fin", ""))[:5]
    for schedule in SHIFT_SCHEDULES[selected_operation]:
        if schedule["start"] == start and schedule["end"] == end:
            return schedule["label"]
    return str(row.get("tipo_turno", "Turno")).title()


def incident_summary(data):
    if data.empty:
        return data
    columns = ["tipo", "hora_inicio", "hora_fin", "duracion_minutos", "estado"]
    view = data[[column for column in columns if column in data]].copy()
    return view.rename(columns={
        "tipo": "Tipo", "hora_inicio": "Inicio", "hora_fin": "Fin",
        "duracion_minutos": "Duración (min)", "estado": "Estado",
    })


def transfer_summary(data):
    if data.empty:
        return data
    columns = ["hora_traslado", "labor_origen", "labor_destino", "cantidad_personas", "motivo"]
    view = data[[column for column in columns if column in data]].copy()
    return view.rename(columns={
        "hora_traslado": "Hora", "labor_origen": "Origen", "labor_destino": "Destino",
        "cantidad_personas": "Personas", "motivo": "Motivo",
    })


def display_clock(value, fallback=None):
    if value is None or pd.isna(value) or str(value).strip() in ("", "None", "NaT"):
        return fallback or "Pendiente"
    text = str(value)
    if "T" not in text and len(text) >= 5:
        return text[:5]
    try:
        return pd.to_datetime(value).strftime("%H:%M")
    except (TypeError, ValueError):
        return text[:5]


def turn_summary(data):
    rows = []
    for _, item in data.head(30).iterrows():
        personal = frame(T["personal"], {"turno_id": str(item["id"])})
        if personal.empty:
            personal = pd.DataFrame([{"labor": "Sin distribución", "cantidad_personas": 0,
                                      "hora_inicio": None, "hora_fin": None}])
        for _, detail in personal.iterrows():
            quantity = detail.get("cantidad_personas", 0)
            quantity = 0 if pd.isna(quantity) else int(quantity)
            rows.append({
                "Subproceso": detail.get("labor", "Sin distribución"),
                "Personal": quantity,
                "Estado": STATUS_LABELS.get(item["estado"], item["estado"]),
                "Hora inicio": display_clock(
                    detail.get("hora_inicio"), str(item.get("hora_programada_inicio", ""))[:5]
                ),
                "Hora final": display_clock(detail.get("hora_fin")),
            })
    return pd.DataFrame(rows)


def today_turns(data):
    if data.empty or "fecha" not in data:
        return data
    today_value = str(datetime.now(LIMA).date())
    return data[data["fecha"].astype(str) == today_value]


def render_daily_turn_table(data, key):
    today_value = datetime.now(LIMA).date()
    st.markdown(f"**Fecha: {today_value.strftime('%d/%m/%Y')}**")
    daily = today_turns(data)
    if daily.empty:
        st.info("No hay turnos registrados para hoy.")
        return
    daily = daily.copy()
    daily["_turno_visible"] = [shift_label_for_row(row) for _, row in daily.iterrows()]
    ordered_shifts = [item["label"] for item in SHIFT_SCHEDULES[selected_operation]]
    available_shifts = [shift for shift in ordered_shifts if shift in set(daily["_turno_visible"])]
    for shift in daily["_turno_visible"].dropna().unique():
        if shift not in available_shifts:
            available_shifts.append(shift)
    selected_shift = st.selectbox("Turno", available_shifts, key=key)
    selected_rows = daily[daily["_turno_visible"] == selected_shift].drop(columns=["_turno_visible"])
    st.dataframe(turn_summary(selected_rows), width="stretch", hide_index=True)


def choose_turn(statuses, assistant_id=None):
    data = filter_current_operation(frame(T["turnos"]))
    if not data.empty:
        data = data[data["estado"].isin(statuses)]
    if assistant_id and not data.empty:
        data = data[data["asistente_id"].astype(str) == str(assistant_id)]
    if data.empty:
        return None
    mapping = {turn_label(row): str(row["id"]) for _, row in data.iterrows()}
    if assistant_id:
        preferred_key = f"active_turn_{assistant_id}_{selected_operation}"
        preferred_id = str(st.session_state.get(preferred_key, ""))
        selected_row = data[data["id"].astype(str) == preferred_id]
        if selected_row.empty:
            selected_row = data.head(1)
        selected_id = str(selected_row.iloc[0]["id"])
        selected_label = turn_label(selected_row.iloc[0])
        st.info(f"Operación actual: {selected_label}")
        st.session_state[preferred_key] = selected_id
        return selected_id
    if len(mapping) == 1:
        label, turn_id = next(iter(mapping.items()))
        st.info(f"Operación seleccionada: {label}")
        return turn_id
    return mapping[st.selectbox("Operación aprobada", list(mapping))]


def render_module_cards(current_role):
    if current_role == "JEFATURA":
        items = [
            ("Planificación", "Programa recursos, turnos y responsables."),
            ("Reportes", "Analiza resultados, incidencias y cumplimiento."),
            ("Administración", "Gestiona usuarios, accesos y configuraciones."),
        ]
    elif current_role == "SUPERVISOR":
        items = [
            ("Operaciones", "Valida aperturas, seguimiento y cierres."),
            ("Reportes", "Revisa los resultados reales de su operación."),
        ]
    else:
        items = [
            ("Planificación", "Consulta lo programado para la jornada."),
            ("Operaciones", "Registra y controla la ejecución del turno."),
            ("Reportes", "Revisa resultados e incidencias."),
        ]
    for index, (column, (title, description)) in enumerate(zip(st.columns(len(items)), items)):
        with column.container(border=True):
            st.subheader(title)
            st.caption(description)
            if st.button(
                "Ingresar",
                key=f"dashboard_module_{current_role}_{index}",
                type="primary",
                use_container_width=True,
            ):
                if current_role == "ASISTENTE":
                    st.session_state["assistant_entry_module"] = title
                    st.session_state["main_navigation_ASISTENTE"] = title
                else:
                    st.session_state[f"current_section_{current_role}"] = title
                st.rerun()

def render_planning_view():
    if role == "JEFATURA":
        st.title("Planificación general")
        st.caption("Define las metas del día que utilizará el Dashboard consolidado.")
        plan_date = st.date_input("Fecha de planificación", datetime.now(LIMA).date())
        plan_date_text = str(plan_date)
        current_plan = load_daily_plan(plan_date_text)

        st.subheader("Metas de movimiento de jabas")
        c1, c2 = st.columns(2)
        planned_received = c1.number_input(
            "Jabas planificadas para recibir en acopios",
            min_value=0,
            max_value=10000000,
            value=int(current_plan.get("jabas_recibidas", 0) or 0),
            step=100,
        )
        planned_packing = c2.number_input(
            "Jabas planificadas para enviar a packing",
            min_value=0,
            max_value=10000000,
            value=int(current_plan.get("jabas_packing", 0) or 0),
            step=100,
        )

        st.subheader("Personal planificado por proceso")
        plan_rows = []
        for operation in [item["name"] for item in OPERACIONES]:
            process_plan = current_plan.get("procesos", {}).get(operation, {})
            plan_rows.append({
                "Proceso": operation,
                "Personal planificado": int(process_plan.get("personal", 0) or 0),
            })
        people_editor = st.data_editor(
            pd.DataFrame(plan_rows),
            hide_index=True,
            use_container_width=True,
            disabled=["Proceso"],
            column_config={
                "Proceso": st.column_config.TextColumn("Proceso"),
                "Personal planificado": st.column_config.NumberColumn(
                    "Personal planificado", min_value=0, step=1, required=True
                ),
            },
            key=f"daily_plan_people_{plan_date_text}",
        )
        if st.button("Guardar planificación del día", type="primary", use_container_width=True):
            processes = {}
            for _, plan_row in people_editor.iterrows():
                quantity = plan_row.get("Personal planificado", 0)
                quantity = 0 if pd.isna(quantity) else int(quantity)
                processes[str(plan_row["Proceso"])] = {"personal": quantity}
            save_daily_plan(plan_date_text, {
                "jabas_recibidas": int(planned_received),
                "jabas_packing": int(planned_packing),
                "procesos": processes,
            })
            st.success("Planificación guardada. El Dashboard ya usará estas metas.")

        st.divider()
        st.subheader("Horarios programados")
        schedules = pd.DataFrame([
            {
                "Operación": operation,
                "Turno": item["label"],
                "Inicio": item["start"],
                "Fin": item["end"],
            }
            for operation, items in SHIFT_SCHEDULES.items()
            for item in items
        ])
        planned = today_turns(frame(T["turnos"]))
    else:
        st.title(f"Planificación · {selected_operation}")
        st.caption("Vista de la programación de turnos y recursos.")
        schedules = pd.DataFrame([
            {"Turno": item["label"], "Inicio": item["start"], "Fin": item["end"]}
            for item in SHIFT_SCHEDULES[selected_operation]
        ])
        if role == "ASISTENTE":
            planned = filter_current_operation(frame(T["turnos"], {"asistente_id": user_id}))
        else:
            planned = filter_current_operation(frame(T["turnos"]))
        planned = today_turns(planned)
    st.dataframe(schedules, width="stretch", hide_index=True)
    st.metric("Turnos programados para hoy", len(planned))
    if role == "ASISTENTE":
        st.info("El asistente consulta la planificación. La modificación corresponde al supervisor o Jefatura.")
    elif role == "SUPERVISOR":
        st.info("El supervisor revisa la planificación y valida los recursos de su operación.")
    else:
        st.info("Jefatura consolida la planificación general y las asignaciones.")

def render_reports_view():
    if role == "JEFATURA":
        st.title("Reportes")
        operation_names = [ALL_OPERATIONS] + [operation["name"] for operation in OPERACIONES]
        report_operation = st.selectbox("Proceso", operation_names, key="management_report_operation")
        turns = frame(T["turnos"])
        if report_operation != ALL_OPERATIONS and not turns.empty:
            turns = turns[
                turns["responsable_operacion"].fillna("").astype(str) == report_operation
            ]
    else:
        st.title(f"Reportes · {selected_operation}")
        if role == "ASISTENTE":
            turns = filter_current_operation(frame(T["turnos"], {"asistente_id": user_id}))
        else:
            turns = filter_current_operation(frame(T["turnos"]))

    daily_turns = today_turns(turns)
    c1, c2, c3 = st.columns(3)
    c1.metric("Turnos del día", len(daily_turns))
    c2.metric(
        "Finalizados",
        int((daily_turns["estado"] == "VALIDADO").sum()) if not daily_turns.empty else 0,
    )
    turn_ids = set(daily_turns["id"].astype(str)) if not daily_turns.empty else set()
    incidents = frame(T["inc"])
    if not incidents.empty and turn_ids:
        incidents = incidents[incidents["turno_id"].astype(str).isin(turn_ids)]
    else:
        incidents = pd.DataFrame()
    c3.metric("Incidencias", len(incidents))

    if role == "JEFATURA":
        if daily_turns.empty:
            st.info("No hay datos registrados para hoy.")
        else:
            columns = [
                "responsable_operacion", "tipo_turno", "estado",
                "hora_programada_inicio", "hora_programada_fin",
            ]
            view = daily_turns[[column for column in columns if column in daily_turns]].copy()
            view = view.rename(columns={
                "responsable_operacion": "Proceso",
                "tipo_turno": "Turno",
                "estado": "Estado",
                "hora_programada_inicio": "Hora inicio",
                "hora_programada_fin": "Hora final",
            })
            st.dataframe(view, width="stretch", hide_index=True)
    else:
        render_daily_turn_table(daily_turns, f"reports_daily_{role}_{selected_operation}")

    if not incidents.empty:
        with st.expander("Ver incidencias del día"):
            st.dataframe(incident_summary(incidents), width="stretch", hide_index=True)

if role == "ASISTENTE" and page == "Planificación":
    render_planning_view()

elif role == "ASISTENTE" and page == "Reportes":
    render_reports_view()

elif role == "ASISTENTE" and page == "Inicio":
    st.title("Inicio")
    st.caption(f"Operación seleccionada: {selected_operation}")
    render_module_cards(role)
    st.subheader("Resumen de hoy")
    data = filter_current_operation(frame(T["turnos"], {"asistente_id": user_id}))
    render_daily_turn_table(data, "assistant_daily_shift")

elif role == "ASISTENTE" and page == "Abrir turno":
    st.title("Abrir turno")
    opening_result_key = f"opening_result_{user_id}_{selected_operation}"
    pending_opening = assistant_active_data[
        assistant_active_data["estado"] == "ABIERTO"
    ].head(1) if not assistant_active_data.empty else pd.DataFrame()
    if not pending_opening.empty:
        turn = pending_opening.iloc[0]
        turn_id = str(turn["id"])
        st.subheader("Turno enviado al supervisor")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Fecha", str(turn.get("fecha", "")))
        c2.metric("Turno", shift_label_for_row(turn))
        c3.metric(
            "Horario",
            f"{str(turn.get('hora_programada_inicio', ''))[:5]} – "
            f"{str(turn.get('hora_programada_fin', ''))[:5]}",
        )
        c4.metric("Estado", STATUS_LABELS.get(str(turn.get("estado")), str(turn.get("estado"))))

        personal = frame(T["personal"], {"turno_id": turn_id})
        if not personal.empty:
            st.markdown("#### Personal enviado")
            personal_view = personal[["labor", "cantidad_personas"]].rename(columns={
                "labor": "Labor o integrante", "cantidad_personas": "Personal",
            })
            st.dataframe(personal_view, width="stretch", hide_index=True)

        observation = str(turn.get("observacion_apertura") or "").strip()
        if observation:
            with st.expander("Ver detalle enviado"):
                st.write(observation)
        st.info("Pendiente de confirmación del supervisor.")
        st.stop()
    with st.form("open"):
        c1, c2 = st.columns(2)
        day = c1.date_input("Fecha", date.today())
        schedules = SHIFT_SCHEDULES[selected_operation]
        schedule_by_label = {item["label"]: item for item in schedules}
        shift = c2.selectbox("Turno", list(schedule_by_label))
        selected_schedule = schedule_by_label[shift]
        c1, c2 = st.columns(2)
        start = c1.time_input("Inicio", time.fromisoformat(selected_schedule["start"]), disabled=True)
        end = c2.time_input("Fin programado", time.fromisoformat(selected_schedule["end"]), disabled=True)
        opening_labors = LABORES
        operation_detail = ""
        if selected_operation == "Acopios":
            st.markdown("#### Punto de acopio")
            selected_acopio = st.selectbox("Ubicación", list(ACOPIOS))
            acopio_data = ACOPIOS[selected_acopio]
            c1, c2 = st.columns(2)
            c1.metric("Tipo", acopio_data["tipo"])
            c2.metric("Capacidad", f"{acopio_data['capacidad']:,} jabas")
            opening_labors = ["Asistente (acopiador)", "Estibadores"]
            if acopio_data["tipo"] == "Mecanizado":
                opening_labors.append("Montacarguistas")
            operation_detail = (
                f"ACOPIO: ubicación={selected_acopio}, tipo={acopio_data['tipo']}, "
                f"capacidad={acopio_data['capacidad']} jabas."
            )
        st.markdown("#### Personal por labor o integrante")
        default_quantities = [10, 4, 2] if selected_operation == "Lavado de jabas" else [0] * len(opening_labors)
        quantities = [
            st.number_input(labor, 0, 200, value)
            for labor, value in zip(opening_labors, default_quantities)
        ]
        if selected_operation == "Acarreo de fruta":
            st.markdown("#### Equipos — Lote → Acopio")
            c1, c2, c3 = st.columns(3)
            la_motofurgones = c1.number_input("Motofurgones", 0, 100, 0, key="la_motofurgones")
            la_personal_moto = c2.number_input("Personal por motofurgón", 0, 10, 1, key="la_personal_moto")
            la_tractores = c3.number_input("Tractores", 0, 100, 0, key="la_tractores")
            c1, c2 = st.columns(2)
            la_personal_tractor = c1.number_input("Personal por tractor", 0, 10, 1, key="la_personal_tractor")
            la_carretas = c2.number_input("Carretas", 0, 200, 0, key="la_carretas")
            st.markdown("#### Equipos — Acopio → Packing")
            c1, c2, c3 = st.columns(3)
            ap_tractores = c1.number_input("Tractores ", 0, 100, 0, key="ap_tractores")
            ap_personal_tractor = c2.number_input("Personal por tractor ", 0, 10, 1, key="ap_personal_tractor")
            ap_carretas = c3.number_input("Carretas ", 0, 200, 0, key="ap_carretas")
            exceptional_moto = st.checkbox("Uso excepcional de motofurgón en Acopio → Packing")
            ap_motofurgones = ap_personal_moto = 0
            exceptional_reason = ""
            if exceptional_moto:
                c1, c2 = st.columns(2)
                ap_motofurgones = c1.number_input("Motofurgones excepcionales", 1, 100, 1)
                ap_personal_moto = c2.number_input("Personal por motofurgón excepcional", 1, 10, 1)
                exceptional_reason = st.text_input("Motivo de la excepción")
            operation_detail = (
                f"RECURSOS Lote-Acopio: motofurgones={la_motofurgones}, personal/motofurgón={la_personal_moto}, "
                f"tractores={la_tractores}, personal/tractor={la_personal_tractor}, carretas={la_carretas}. "
                f"Acopio-Packing: tractores={ap_tractores}, personal/tractor={ap_personal_tractor}, "
                f"carretas={ap_carretas}, motofurgones_excepcionales={ap_motofurgones}, "
                f"personal/motofurgón={ap_personal_moto}, motivo={exceptional_reason or 'No aplica'}."
            )
        observation = st.text_area("Observación")
        if st.form_submit_button("Enviar al supervisor", type="primary", use_container_width=True):
            try:
                shift_code = selected_schedule["code"]
                existing_df = filter_current_operation(pd.DataFrame(get(T["turnos"], {
                    "fecha": str(day), "tipo_turno": shift_code, "asistente_id": user_id,
                })))
                if not existing_df.empty:
                    existing_df = existing_df[
                        existing_df["hora_programada_inicio"].astype(str).str[:5] == selected_schedule["start"]
                    ]
                if selected_operation == "Acopios" and not existing_df.empty:
                    existing_df = existing_df[
                        existing_df["observacion_apertura"].fillna("").astype(str).str.contains(
                            f"ubicación={selected_acopio},", regex=False
                        )
                    ]
                existing = existing_df.to_dict("records")
                if existing:
                    st.session_state[f"active_turn_{user_id}_{selected_operation}"] = str(existing[0]["id"])
                    st.session_state[opening_result_key] = {
                        "fecha": str(day), "turno": shift, "estado": existing[0]["estado"],
                    }
                else:
                    row = add(T["turnos"], {
                        "fecha": str(day), "tipo_turno": shift_code,
                        "hora_programada_inicio": start.strftime("%H:%M"),
                        "hora_programada_fin": end.strftime("%H:%M"),
                        "asistente_id": user_id, "responsable_operacion": selected_operation,
                        "estado": "ABIERTO",
                        "observacion_apertura": "\n".join(filter(None, [observation, operation_detail])),
                        "creado_en": now(), "actualizado_en": now(),
                    })
                    turn_id = row["id"]
                    st.session_state[f"active_turn_{user_id}_{selected_operation}"] = str(turn_id)
                    add(T["personal"], [{
                        "turno_id": turn_id, "labor": labor, "cantidad_personas": quantity,
                        "hora_inicio": timestamp(day, start), "minutos_refrigerio": 45,
                        "creado_en": now(),
                    } for labor, quantity in zip(opening_labors, quantities)])
                    audit("turnos", turn_id, "estado", None, "ABIERTO",
                          f"Personal inicial: {sum(quantities)}", user_id)
                    st.session_state[opening_result_key] = {
                        "fecha": str(day), "turno": shift, "estado": "ABIERTO",
                    }
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo crear el turno: {getattr(e, 'message', None) or str(e)}")

elif role == "ASISTENTE" and page == "Operación":
    st.title("Operación en curso")
    turn_id = choose_turn(["CONFIRMADO"], user_id)
    if turn_id is None:
        st.info("No tienes turnos en ejecución.")
    else:
        tab_names = ["Incidencias", "Traslado interno"]
        if selected_operation == "Acopios":
            tab_names.append("Viajes")
        operation_tabs = st.tabs(tab_names)
        incident_tab, transfer_tab = operation_tabs[:2]
        with incident_tab:
            with st.form("inc"):
                incident_type = st.selectbox("Tipo", INCIDENCIAS)
                c1, c2 = st.columns(2)
                start = c1.time_input("Inicio", datetime.now(LIMA).time().replace(second=0, microsecond=0))
                close_now = c2.checkbox("Cerrar ahora")
                end = st.time_input(
                    "Fin",
                    datetime.now(LIMA).time().replace(second=0, microsecond=0),
                    help="Esta hora solo se guardará si marcas 'Cerrar ahora'.",
                )
                description = st.text_area("Descripción")
                if st.form_submit_button("Guardar"):
                    start_dt = datetime.combine(date.today(), start, tzinfo=LIMA)
                    end_dt = datetime.combine(date.today(), end, tzinfo=LIMA) if close_now else None
                    if end_dt and end_dt <= start_dt:
                        end_dt += timedelta(days=1)
                    add(T["inc"], {
                        "turno_id": turn_id, "tipo": incident_type, "descripcion": description,
                        "hora_inicio": start_dt.isoformat(timespec="seconds"),
                        "hora_fin": end_dt.isoformat(timespec="seconds") if end_dt else None,
                        "duracion_minutos": minutes_between(start_dt, end_dt) if end_dt else None,
                        "estado": "CERRADA" if close_now else "ABIERTA",
                        "registrado_por": user_id, "creado_en": now(),
                    })
                    st.rerun()
            incidents = frame(T["inc"], {"turno_id": turn_id})
            if incidents.empty:
                st.info("Sin incidencias registradas.")
            else:
                st.dataframe(incident_summary(incidents), width="stretch", hide_index=True)
                open_incidents = incidents[incidents["estado"] == "ABIERTA"]
                if not open_incidents.empty:
                    st.subheader("Cerrar incidencia abierta")
                    incident_options = {
                        f"{row['tipo']} | Inicio: {pd.to_datetime(row['hora_inicio']).strftime('%H:%M')}": str(row["id"])
                        for _, row in open_incidents.iterrows()
                    }
                    selected_incident = st.selectbox("Incidencia", list(incident_options))
                    closing_time = st.time_input(
                        "Hora final de la incidencia",
                        datetime.now(LIMA).time().replace(second=0, microsecond=0),
                        key="incident_closing_time",
                    )
                    if st.button("Cerrar incidencia", type="primary", use_container_width=True):
                        incident_id = incident_options[selected_incident]
                        incident_row = open_incidents[open_incidents["id"].astype(str) == incident_id].iloc[0]
                        start_dt = pd.to_datetime(incident_row["hora_inicio"]).to_pydatetime()
                        end_dt = datetime.combine(start_dt.date(), closing_time, tzinfo=LIMA)
                        if end_dt <= start_dt:
                            end_dt += timedelta(days=1)
                        duration = minutes_between(start_dt, end_dt)
                        edit(T["inc"], {
                            "hora_fin": end_dt.isoformat(timespec="seconds"),
                            "duracion_minutos": duration,
                            "estado": "CERRADA",
                        }, {"id": incident_id})
                        audit("incidencias", incident_id, "estado", "ABIERTA", "CERRADA",
                              f"Duración: {duration} minutos", user_id)
                        st.rerun()
        with transfer_tab:
            with st.form("move"):
                c1, c2 = st.columns(2)
                origin = c1.selectbox("Origen", LABORES)
                destination = c2.selectbox("Destino", LABORES, index=1)
                amount = st.number_input("Personas", 1, 200, 1)
                reason = st.text_input("Motivo")
                if st.form_submit_button("Registrar"):
                    if origin == destination:
                        st.error("Origen y destino deben ser distintos.")
                    else:
                        add(T["tras"], {
                            "turno_id": turn_id, "hora_traslado": now(),
                            "labor_origen": origin, "labor_destino": destination,
                            "cantidad_personas": amount, "motivo": reason,
                            "registrado_por": user_id, "creado_en": now(),
                        })
                        st.rerun()
            transfers = frame(T["tras"], {"turno_id": turn_id})
            if transfers.empty:
                st.info("Sin traslados registrados.")
            else:
                st.dataframe(transfer_summary(transfers), width="stretch", hide_index=True)

        if selected_operation == "Acopios":
            trip_tab = operation_tabs[2]
            with trip_tab:
                location = turn_acopio(turn_id)
                if location is None:
                    st.warning("Este turno no tiene un punto de acopio asociado. Selecciónalo para la prueba.")
                    location = st.selectbox("Punto de acopio", list(ACOPIOS), key="trip_fallback_acopio")
                acopio_data = ACOPIOS[location]
                st.subheader(location)
                c1, c2 = st.columns(2)
                c1.metric("Tipo", acopio_data["tipo"])
                c2.metric("Capacidad", f"{acopio_data['capacidad']:,} jabas")

                trips = acopio_trips(turn_id)
                entries = acopio_entries(turn_id)
                received_jabas = sum(int(item.get("total_jabas", 0) or 0) for item in entries)
                sent_jabas = sum(int(item.get("total_jabas", 0) or 0) for item in trips)
                in_transit = [item for item in trips if item.get("estado") == "EN_TRANSITO"]
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Jabas recibidas", f"{received_jabas:,}")
                c2.metric("Jabas enviadas a packing", f"{sent_jabas:,}")
                c3.metric("Saldo en acopio", f"{max(received_jabas - sent_jabas, 0):,}")
                c4.metric("Viajes en tránsito", len(in_transit))

                st.markdown("#### Registrar recepción en acopio")
                with st.form("register_acopio_entry", clear_on_submit=True):
                    c1, c2, c3 = st.columns(3)
                    origin = c1.text_input("Procedencia o lote")
                    delivered_by = c2.text_input("Responsable de entrega")
                    entry_time = c3.time_input(
                        "Hora de recepción", datetime.now(LIMA).time().replace(second=0, microsecond=0)
                    )
                    entry_editor = st.data_editor(
                        pd.DataFrame([{"Variedad": "", "Jabas": 0}]),
                        num_rows="dynamic",
                        hide_index=True,
                        use_container_width=True,
                        column_config={
                            "Variedad": st.column_config.TextColumn("Variedad", required=True),
                            "Jabas": st.column_config.NumberColumn(
                                "Jabas", min_value=0, step=1, required=True
                            ),
                        },
                        key="entry_varieties_editor",
                    )
                    if st.form_submit_button(
                        "Registrar recepción", type="primary", use_container_width=True
                    ):
                        details = []
                        for _, detail in entry_editor.iterrows():
                            variety = str(detail.get("Variedad") or "").strip()
                            amount = detail.get("Jabas", 0)
                            amount = 0 if pd.isna(amount) else int(amount)
                            if variety and amount > 0:
                                details.append({"variedad": variety, "jabas": amount})
                        if not origin.strip():
                            st.error("Indica la procedencia o lote.")
                        elif not delivered_by.strip():
                            st.error("Indica el responsable de entrega.")
                        elif not details:
                            st.error("Agrega al menos una variedad con cantidad de jabas.")
                        else:
                            turn = frame(T["turnos"], {"id": turn_id}).iloc[0]
                            entry_day = date.fromisoformat(str(turn["fecha"]))
                            entry_datetime = datetime.combine(entry_day, entry_time, tzinfo=LIMA)
                            entry = {
                                "numero": len(entries) + 1,
                                "acopio": location,
                                "procedencia": origin.strip(),
                                "responsable_entrega": delivered_by.strip(),
                                "hora": entry_datetime.isoformat(timespec="seconds"),
                                "variedades": details,
                                "total_jabas": sum(item["jabas"] for item in details),
                                "registrado_por": user_id,
                            }
                            save_acopio_entry(turn_id, entry)
                            audit(
                                "ingresos_acopio", turn_id, "recepcion", None,
                                entry["total_jabas"], f"{location} · {origin.strip()}", user_id
                            )
                            st.rerun()

                if entries:
                    with st.expander("Ver recepciones registradas"):
                        entry_rows = []
                        for item in entries:
                            varieties = ", ".join(
                                f"{detail['variedad']}: {detail['jabas']}"
                                for detail in item.get("variedades", [])
                            )
                            entry_rows.append({
                                "Recepción": item.get("numero"),
                                "Hora": display_clock(item.get("hora")),
                                "Procedencia": item.get("procedencia"),
                                "Responsable": item.get("responsable_entrega"),
                                "Jabas": item.get("total_jabas", 0),
                                "Variedades": varieties,
                            })
                        st.dataframe(pd.DataFrame(entry_rows), width="stretch", hide_index=True)

                st.markdown("#### Registrar salida")
                with st.form("register_acopio_trip", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    unit = c1.text_input("Unidad", placeholder="Código o placa")
                    departure_time = c2.time_input(
                        "Hora de salida", datetime.now(LIMA).time().replace(second=0, microsecond=0)
                    )
                    st.caption("Agrega una fila por cada variedad transportada.")
                    varieties_editor = st.data_editor(
                        pd.DataFrame([{"Variedad": "", "Jabas": 0}]),
                        num_rows="dynamic",
                        hide_index=True,
                        use_container_width=True,
                        column_config={
                            "Variedad": st.column_config.TextColumn("Variedad", required=True),
                            "Jabas": st.column_config.NumberColumn("Jabas", min_value=0, step=1, required=True),
                        },
                        key="trip_varieties_editor",
                    )
                    register_trip = st.form_submit_button(
                        "Registrar salida", type="primary", use_container_width=True
                    )
                    if register_trip:
                        details = []
                        for _, detail in varieties_editor.iterrows():
                            variety = str(detail.get("Variedad") or "").strip()
                            amount = detail.get("Jabas", 0)
                            amount = 0 if pd.isna(amount) else int(amount)
                            if variety and amount > 0:
                                details.append({"variedad": variety, "jabas": amount})
                        normalized_unit = unit.strip().upper()
                        duplicate_unit = any(
                            str(item.get("unidad", "")).upper() == normalized_unit for item in in_transit
                        )
                        if not normalized_unit:
                            st.error("Ingresa la unidad que realiza el viaje.")
                        elif duplicate_unit:
                            st.error("Esa unidad ya tiene un viaje en tránsito.")
                        elif not details:
                            st.error("Agrega al menos una variedad con cantidad de jabas.")
                        else:
                            turn = frame(T["turnos"], {"id": turn_id}).iloc[0]
                            turn_day = date.fromisoformat(str(turn["fecha"]))
                            departure = datetime.combine(turn_day, departure_time, tzinfo=LIMA)
                            programmed_start = time.fromisoformat(str(turn["hora_programada_inicio"])[:5])
                            programmed_end = time.fromisoformat(str(turn["hora_programada_fin"])[:5])
                            if programmed_end <= programmed_start and departure_time < programmed_start:
                                departure += timedelta(days=1)
                            next_number = max([int(item.get("numero", 0) or 0) for item in trips] + [0]) + 1
                            trip = {
                                "numero": next_number, "acopio": location,
                                "tipo_acopio": acopio_data["tipo"], "capacidad": acopio_data["capacidad"],
                                "unidad": normalized_unit,
                                "salida": departure.isoformat(timespec="seconds"),
                                "llegada": None, "duracion_minutos": None,
                                "variedades": details,
                                "total_jabas": sum(item["jabas"] for item in details),
                                "estado": "EN_TRANSITO", "registrado_por": user_id,
                            }
                            save_acopio_trip(turn_id, trip)
                            audit("viajes_acopio", turn_id, "salida", None, next_number,
                                  f"Unidad {normalized_unit} · {location}", user_id)
                            st.rerun()

                if in_transit:
                    st.markdown("#### Registrar llegada")
                    trip_options = {
                        f"Viaje {item['numero']} · {item['unidad']} · salida {display_clock(item['salida'])}": item
                        for item in in_transit
                    }
                    selected_trip_label = st.selectbox("Viaje en tránsito", list(trip_options))
                    arrival_time = st.time_input(
                        "Hora de llegada", datetime.now(LIMA).time().replace(second=0, microsecond=0),
                        key="trip_arrival_time",
                    )
                    if st.button("Registrar llegada", type="primary", use_container_width=True):
                        selected_trip = dict(trip_options[selected_trip_label])
                        key = selected_trip.pop("_key")
                        departure = pd.to_datetime(selected_trip["salida"]).to_pydatetime()
                        arrival = datetime.combine(departure.date(), arrival_time, tzinfo=LIMA)
                        if arrival < departure:
                            arrival += timedelta(days=1)
                        selected_trip["llegada"] = arrival.isoformat(timespec="seconds")
                        selected_trip["duracion_minutos"] = minutes_between(departure, arrival)
                        selected_trip["estado"] = "FINALIZADO"
                        update_acopio_trip(key, selected_trip)
                        audit("viajes_acopio", turn_id, "llegada", None, selected_trip["numero"],
                              f"Duración: {selected_trip['duracion_minutos']} minutos", user_id)
                        st.rerun()

                if trips:
                    rows = []
                    for item in trips:
                        varieties = ", ".join(
                            f"{detail['variedad']}: {detail['jabas']}" for detail in item.get("variedades", [])
                        )
                        rows.append({
                            "Viaje": item.get("numero"), "Unidad": item.get("unidad"),
                            "Salida": display_clock(item.get("salida")),
                            "Llegada": display_clock(item.get("llegada")),
                            "Duración (min)": item.get("duracion_minutos") or "Pendiente",
                            "Jabas": item.get("total_jabas", 0), "Variedades": varieties,
                            "Estado": "En tránsito" if item.get("estado") == "EN_TRANSITO" else "Finalizado",
                        })
                    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

        st.divider()
        if st.button("Continuar al cierre del turno", type="primary", use_container_width=True):
            st.session_state[f"assistant_close_mode_{user_id}_{selected_operation}"] = True
            st.rerun()

elif role == "ASISTENTE" and page == "Cerrar turno":
    st.title("Cerrar turno")
    submitted_closure = assistant_active_data[
        assistant_active_data["estado"] == "CERRADO"
    ].head(1) if not assistant_active_data.empty else pd.DataFrame()
    if not submitted_closure.empty:
        turn = submitted_closure.iloc[0]
        turn_id = str(turn["id"])
        st.subheader("Cierre enviado al supervisor")
        c1, c2, c3 = st.columns(3)
        c1.metric("Fecha", str(turn.get("fecha", "")))
        c2.metric("Turno", shift_label_for_row(turn))
        c3.metric("Estado", STATUS_LABELS.get(str(turn.get("estado")), str(turn.get("estado"))))
        production = frame(T["prod"], {"turno_id": turn_id})
        if not production.empty:
            result_label = RESULT_LABELS[selected_operation]
            st.metric(result_label, f"{int(production.iloc[0].get('jabas_lavadas', 0) or 0):,}")
        st.info("Pendiente de validación del supervisor.")
        st.stop()
    turn_id = choose_turn(["CONFIRMADO"], user_id)
    if turn_id is None:
        st.info("No hay turnos disponibles.")
    else:
        personal = frame(T["personal"], {"turno_id": turn_id})
        turn = frame(T["turnos"], {"id": turn_id}).iloc[0]
        result_label = RESULT_LABELS[selected_operation]
        with st.form("close"):
            end = st.time_input("Hora final real", time.fromisoformat(str(turn["hora_programada_fin"])[:5]))
            result_quantity = st.number_input(result_label, 0, 1000000, 0, step=100)
            observation = st.text_area("Observación de cierre")
            if st.form_submit_button("Enviar cierre", type="primary"):
                end_dt = datetime.combine(date.fromisoformat(str(turn["fecha"])), end, tzinfo=LIMA)
                start_clock = time.fromisoformat(str(turn["hora_programada_inicio"])[:5])
                start_dt = datetime.combine(date.fromisoformat(str(turn["fecha"])), start_clock, tzinfo=LIMA)
                if end_dt <= start_dt:
                    end_dt += timedelta(days=1)
                total_hours_person = 0.0
                for _, item in personal.iterrows():
                    initial = pd.to_datetime(item["hora_inicio"]).to_pydatetime()
                    worked_minutes = minutes_between(initial, end_dt)
                    break_minutes = 45 if worked_minutes > 360 else 0
                    effective_hours = max(worked_minutes - break_minutes, 0) / 60
                    hours_person = effective_hours * int(item["cantidad_personas"])
                    total_hours_person += hours_person
                    edit(T["personal"], {
                        "hora_fin": end_dt.isoformat(timespec="seconds"),
                        "minutos_refrigerio": break_minutes,
                        "horas_efectivas": effective_hours, "horas_persona": hours_person,
                    }, {"id": str(item["id"])})
                productivity = result_quantity / total_hours_person if total_hours_person else 0
                payload = {"turno_id": turn_id, "jabas_lavadas": result_quantity,
                           "horas_persona": total_hours_person, "productividad": productivity,
                           "actualizado_en": now()}
                if get(T["prod"], {"turno_id": turn_id}):
                    edit(T["prod"], payload, {"turno_id": turn_id})
                else:
                    payload["creado_en"] = now()
                    add(T["prod"], payload)
                edit(T["turnos"], {"estado": "CERRADO", "hora_real_fin": end_dt.isoformat(timespec="seconds"),
                                    "observacion_cierre": observation, "cerrado_en": now(), "actualizado_en": now()},
                     {"id": turn_id})
                audit("turnos", turn_id, "estado", "CONFIRMADO", "CERRADO",
                      f"{result_label}: {result_quantity}", user_id)
                st.session_state.pop(f"assistant_close_mode_{user_id}_{selected_operation}", None)
                st.rerun()

elif role == "SUPERVISOR" and page == "Planificación":
    render_planning_view()

elif role == "SUPERVISOR" and page == "Reportes":
    render_reports_view()

elif role == "SUPERVISOR" and page == "Panel":
    st.title(f"Dashboard · {selected_operation}")
    render_module_cards(role)
    st.subheader("Estado de hoy")
    data = today_turns(filter_current_operation(frame(T["turnos"])))
    metric_labels = [("ABIERTO", "Por confirmar"), ("CONFIRMADO", "En ejecución"),
                     ("CERRADO", "Cierres pendientes"), ("VALIDADO", "Finalizados")]
    for column, (status, label_text) in zip(st.columns(4), metric_labels):
        column.metric(label_text, int((data["estado"] == status).sum()) if not data.empty else 0)
    render_daily_turn_table(data, "supervisor_daily_shift")

elif role == "SUPERVISOR" and page == "Confirmar apertura":
    st.title("Confirmar apertura")
    turn_id = choose_turn(["ABIERTO"])
    if turn_id is None:
        st.info("No hay aperturas pendientes.")
    else:
        staff = frame(T["personal"], {"turno_id": turn_id})
        if not staff.empty:
            staff_view = staff[["labor", "cantidad_personas"]].rename(
                columns={"labor": "Labor o integrante", "cantidad_personas": "Personal"}
            )
            st.dataframe(staff_view, width="stretch", hide_index=True)
            st.metric("Personal total", int(staff["cantidad_personas"].fillna(0).sum()))
        if st.button("Confirmar inicio", type="primary"):
            edit(T["turnos"], {"estado": "CONFIRMADO", "supervisor_id": user_id,
                                "hora_real_inicio": now(), "confirmado_en": now(), "actualizado_en": now()},
                 {"id": turn_id})
            audit("turnos", turn_id, "estado", "ABIERTO", "CONFIRMADO",
                  "Apertura validada", user_id)
            st.rerun()

elif role == "SUPERVISOR" and page == "Seguimiento":
    st.title("Seguimiento")
    turn_id = choose_turn(["CONFIRMADO", "CERRADO", "VALIDADO"])
    if turn_id is not None:
        incidents = frame(T["inc"], {"turno_id": turn_id})
        transfers = frame(T["tras"], {"turno_id": turn_id})
        st.subheader("Incidencias")
        if not incidents.empty:
            st.dataframe(incident_summary(incidents), width="stretch", hide_index=True)
        else:
            st.info("Sin incidencias.")
        st.subheader("Traslados")
        if not transfers.empty:
            st.dataframe(transfer_summary(transfers), width="stretch", hide_index=True)
        else:
            st.info("Sin traslados.")
        with st.expander("Ver detalle de auditoría"):
            audit_data = frame(T["audit"], {"registro_id": turn_id})
            if not audit_data.empty:
                st.dataframe(audit_data, width="stretch", hide_index=True)
            else:
                st.info("Sin movimientos de auditoría.")

elif role == "SUPERVISOR" and page == "Validar cierre":
    st.title("Validar cierre")
    turn_id = choose_turn(["CERRADO"])
    if turn_id is None:
        st.info("No hay cierres pendientes.")
    else:
        production = frame(T["prod"], {"turno_id": turn_id}).iloc[0]
        old = int(production["jabas_lavadas"])
        with st.form("validate"):
            result_label = RESULT_LABELS[selected_operation]
            new = st.number_input(result_label, 0, 1000000, old)
            reason = st.text_area("Motivo obligatorio si corrige")
            if st.form_submit_button("Validar", type="primary"):
                if new != old and not reason.strip():
                    st.error("Debe indicar el motivo.")
                else:
                    hours_person = float(production["horas_persona"] or 0)
                    if new != old:
                        edit(T["prod"], {"jabas_lavadas": new,
                                         "productividad": new / hours_person if hours_person else 0,
                                         "actualizado_en": now()}, {"turno_id": turn_id})
                        audit("produccion_turno", str(production["id"]), result_label, old, new, reason, user_id)
                    edit(T["turnos"], {"estado": "VALIDADO", "supervisor_id": user_id,
                                        "validado_en": now(), "actualizado_en": now()}, {"id": turn_id})
                    audit("turnos", turn_id, "estado", "CERRADO", "VALIDADO",
                          "Cierre validado", user_id)
                    st.rerun()

elif role == "JEFATURA" and page == "Usuarios y accesos":
    st.title("Usuarios y accesos")
    st.caption("Jefatura define quién puede ingresar, con qué rol y a qué operación será dirigido.")
    display = all_users[["nombre", "usuario", "rol", "activo"]].copy()
    display["operación"] = [
        "Acceso global" if str(row["rol"]).upper() == "JEFATURA" else assigned_operation(str(row["id"]))
        for _, row in all_users.iterrows()
    ]
    st.dataframe(display, width="stretch", hide_index=True)
    edit_tab, create_tab = st.tabs(["Configurar usuario", "Nuevo usuario"])
    with edit_tab:
        if not all_users.empty:
            user_options = {f"{row['nombre']} · {row['usuario']}": str(row["id"]) for _, row in all_users.iterrows()}
            selected_label = st.selectbox("Usuario a configurar", list(user_options))
            selected_id = user_options[selected_label]
            selected = all_users[all_users["id"].astype(str) == selected_id].iloc[0]
            roles = ["ASISTENTE", "SUPERVISOR", "JEFATURA"]
            selected_name = st.text_input("Nombre", str(selected["nombre"]), key="edit_name")
            selected_username = st.text_input("Usuario", str(selected["usuario"]), key="edit_username")
            selected_role = st.selectbox("Rol", roles, index=roles.index(str(selected["rol"]).upper()))
            selected_active = st.checkbox("Acceso activo", value=bool(selected["activo"]))
            operation_names = [operation["name"] for operation in OPERACIONES]
            current_operation = assigned_operation(selected_id)
            selected_operation = st.selectbox(
                "Operación principal",
                operation_names,
                index=operation_names.index(current_operation) if current_operation in operation_names else 0,
                disabled=selected_role == "JEFATURA",
            )
            if st.button("Guardar cambios", type="primary", use_container_width=True):
                duplicate = all_users[
                    (all_users["usuario"].astype(str).str.lower() == selected_username.strip().lower())
                    & (all_users["id"].astype(str) != selected_id)
                ]
                if not selected_name.strip() or not selected_username.strip():
                    st.error("Nombre y usuario son obligatorios.")
                elif not duplicate.empty:
                    st.error("Ese nombre de usuario ya existe.")
                elif selected_id == user_id and not selected_active:
                    st.error("No puedes desactivar tu propia cuenta mientras estás conectado.")
                else:
                    changes = {"nombre": selected_name.strip(), "usuario": selected_username.strip().lower(),
                               "rol": selected_role, "activo": selected_active}
                    edit(T["users"], changes, {"id": selected_id})
                    old_operation = assigned_operation(selected_id)
                    if selected_role != "JEFATURA":
                        save_assigned_operation(selected_id, selected_operation)
                    for field, old_value, new_value in [
                        ("nombre", selected["nombre"], changes["nombre"]),
                        ("usuario", selected["usuario"], changes["usuario"]),
                        ("rol", str(selected["rol"]).upper(), selected_role),
                        ("activo", bool(selected["activo"]), selected_active),
                    ]:
                        if str(old_value) != str(new_value):
                            audit("app_users", selected_id, field, old_value, new_value,
                                  "Configuración de acceso por Jefatura", user_id)
                    if selected_role != "JEFATURA" and old_operation != selected_operation:
                        audit("app_users", selected_id, "operacion", old_operation, selected_operation,
                              "Asignación de operación por Jefatura", user_id)
                    st.success("Usuario actualizado.")
                    st.rerun()

            st.markdown("#### Restablecer contraseña")
            with st.form(f"reset_password_form_{selected_id}", clear_on_submit=True):
                new_password = st.text_input(
                    "Nueva contraseña", type="password", key=f"reset_password_{selected_id}"
                )
                confirm_password = st.text_input(
                    "Confirmar nueva contraseña", type="password", key=f"confirm_reset_password_{selected_id}"
                )
                reset_password = st.form_submit_button("Restablecer contraseña", use_container_width=True)
                if reset_password:
                    if not new_password:
                        st.error("La contraseña no puede estar vacía.")
                    elif new_password != confirm_password:
                        st.error("Las contraseñas no coinciden.")
                    else:
                        edit(T["users"], {"clave_hash": hash_password(new_password)}, {"id": selected_id})
                        audit("app_users", selected_id, "clave_hash", "Protegido", "Actualizado",
                              "Restablecimiento de contraseña por Jefatura", user_id)
                        st.success("Contraseña restablecida correctamente.")

    with create_tab:
        st.caption("Puedes usar un nombre provisional y reemplazarlo cuando recibas la relación oficial.")
        with st.form("create_user", clear_on_submit=True):
            new_name = st.text_input("Nombre", placeholder="Ejemplo: Asistente Turno Día")
            new_username = st.text_input("Usuario", placeholder="Ejemplo: asistente.dia")
            new_role = st.selectbox("Rol", ["ASISTENTE", "SUPERVISOR", "JEFATURA"], key="new_role")
            new_user_password = st.text_input("Contraseña inicial", type="password")
            new_user_password_confirm = st.text_input("Confirmar contraseña", type="password")
            new_user_operation = st.selectbox(
                "Operación principal", [operation["name"] for operation in OPERACIONES], key="new_operation"
            )
            if st.form_submit_button("Crear usuario", type="primary", use_container_width=True):
                duplicate = all_users[all_users["usuario"].astype(str).str.lower() == new_username.strip().lower()]
                if not new_name.strip() or not new_username.strip():
                    st.error("Nombre y usuario son obligatorios.")
                elif not duplicate.empty:
                    st.error("Ese nombre de usuario ya existe.")
                elif not new_user_password:
                    st.error("La contraseña no puede estar vacía.")
                elif new_user_password != new_user_password_confirm:
                    st.error("Las contraseñas no coinciden.")
                else:
                    created = add(T["users"], {"nombre": new_name.strip(),
                                                "usuario": new_username.strip().lower(),
                                                "clave_hash": hash_password(new_user_password),
                                                "rol": new_role, "activo": True,
                                                "creado_en": now()})
                    if new_role != "JEFATURA":
                        save_assigned_operation(str(created["id"]), new_user_operation)
                    audit("app_users", str(created["id"]), "registro", None, "Creado",
                          "Usuario creado por Jefatura", user_id)
                    st.success("Usuario creado correctamente.")
                    st.rerun()

elif role == "JEFATURA" and page == "Planificación":
    render_planning_view()

elif role == "JEFATURA" and page == "Reportes":
    render_reports_view()

elif role == "JEFATURA":
    today_text = str(datetime.now(LIMA).date())
    st.title("Dashboard consolidado")
    st.caption(f"Resumen operativo de todos los procesos · {datetime.now(LIMA).strftime('%d/%m/%Y')}")
    render_management_quick_navigation()
    management_view = st.radio(
        "Vista del Dashboard",
        ["Diseño consolidado", "Datos reales"],
        horizontal=True,
        key="management_dashboard_view_v3",
    )
    if management_view == "Diseño consolidado":
        render_management_budget_demo()
        st.stop()
    data = paged_frame(T["turnos"], {"fecha": today_text})
    if not data.empty and "observacion_apertura" in data:
        data = data[
            ~data["observacion_apertura"].fillna("").astype(str).str.contains(
                "PRUEBA_CARGA", case=False, regex=False
            )
        ]
    daily_plan = load_daily_plan(today_text)
    all_turn_ids = set(data["id"].astype(str)) if not data.empty else set()
    dashboard_personal = frame_for_turn_ids(T["personal"], all_turn_ids)
    dashboard_production = frame_for_turn_ids(T["prod"], all_turn_ids)
    incidents = frame_for_turn_ids(T["inc"], all_turn_ids)
    acopio_data = data[
        data["responsable_operacion"].fillna("").astype(str) == "Acopios"
    ] if not data.empty else pd.DataFrame()
    acopio_turn_ids = set(acopio_data["id"].astype(str)) if not acopio_data.empty else set()
    recorded_received_jabas, reception_count = acopio_entry_totals(acopio_turn_ids)
    if not dashboard_production.empty and acopio_turn_ids:
        acopio_production = dashboard_production[
            dashboard_production["turno_id"].astype(str).isin(acopio_turn_ids)
        ]
        closed_received_jabas = int(pd.to_numeric(
            acopio_production.get("jabas_lavadas", pd.Series(dtype=float)), errors="coerce"
        ).fillna(0).sum())
    else:
        closed_received_jabas = 0
    received_jabas = recorded_received_jabas if reception_count else closed_received_jabas
    packing_jabas, packing_trips = acopio_trip_totals(acopio_turn_ids)
    stock_jabas = max(received_jabas - packing_jabas, 0)
    open_incidents = int(
        (incidents["estado"].astype(str).str.upper() == "ABIERTA").sum()
    ) if not incidents.empty and "estado" in incidents else 0

    planned_received = int(daily_plan.get("jabas_recibidas", 0) or 0)
    planned_packing = int(daily_plan.get("jabas_packing", 0) or 0)

    def plan_delta(actual, planned):
        return f"{actual / planned:.1%} del plan" if planned > 0 else "Sin meta registrada"

    st.subheader("Movimiento de jabas")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Jabas recibidas en acopios",
        f"{received_jabas:,}",
        plan_delta(received_jabas, planned_received),
        delta_color="off",
    )
    c2.metric(
        "Jabas enviadas a packing",
        f"{packing_jabas:,}",
        plan_delta(packing_jabas, planned_packing),
        delta_color="off",
    )
    c3.metric(
        "Jabas en acopios", f"{stock_jabas:,}",
        f"{reception_count} recepciones · {packing_trips} viajes", delta_color="off"
    )
    c4.metric("Incidencias abiertas", open_incidents)

    st.subheader("Estado por proceso")
    st.caption("La evaluación compara el personal registrado con la planificación diaria de Jefatura.")
    process_columns = st.columns(5)
    for operation in [item["name"] for item in OPERACIONES]:
        operation_data = data[
            data["responsable_operacion"].fillna("").astype(str) == operation
        ] if not data.empty else pd.DataFrame()
        turn_ids = set(operation_data["id"].astype(str)) if not operation_data.empty else set()
        if not dashboard_personal.empty and turn_ids:
            process_personal = dashboard_personal[
                dashboard_personal["turno_id"].astype(str).isin(turn_ids)
            ]
            actual_people = int(pd.to_numeric(
                process_personal.get("cantidad_personas", pd.Series(dtype=float)), errors="coerce"
            ).fillna(0).sum())
        else:
            actual_people = 0
        planned_people = int(
            daily_plan.get("procesos", {}).get(operation, {}).get("personal", 0) or 0
        )
        incident_count = 0
        if not incidents.empty and turn_ids:
            process_incidents = incidents[incidents["turno_id"].astype(str).isin(turn_ids)]
            if "estado" in process_incidents:
                process_incidents = process_incidents[
                    process_incidents["estado"].astype(str).str.upper() == "ABIERTA"
                ]
            incident_count = len(process_incidents)
        status_text, status_color = plan_status(
            operation_data, planned_people, actual_people, incident_count
        )
        column = process_columns[[item["name"] for item in OPERACIONES].index(operation)]
        with column.container(border=True):
            st.markdown(f"**{operation}**")
            if status_color == "green":
                st.success(status_text)
            elif status_color == "orange":
                st.warning(status_text)
            elif status_color == "red":
                st.error(status_text)
            else:
                st.info(status_text)
            st.metric("Personal real / plan", f"{actual_people} / {planned_people}")
            st.caption(
                f"Turnos: {len(operation_data)} · En ejecución: "
                f"{int((operation_data['estado'] == 'CONFIRMADO').sum()) if not operation_data.empty else 0}"
            )
            if st.button("Ver reporte", key=f"management_process_{operation}", use_container_width=True):
                st.session_state["management_report_operation"] = operation
                st.session_state["current_section_JEFATURA"] = "Reportes"
                st.rerun()

st.divider()
st.caption("Control de Operaciones Logísticas ")

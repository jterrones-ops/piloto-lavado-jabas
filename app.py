from datetime import date, datetime, time, timedelta
import pandas as pd
import streamlit as st
from supabase import create_client

st.set_page_config(page_title="Piloto Lavado de Jabas", page_icon="🧼", layout="wide")

T = {
    "users": "app_users", "turnos": "turnos", "personal": "personal_labor",
    "inc": "incidencias", "tras": "traslados_personal",
    "prod": "produccion_turno", "audit": "auditoria",
}
LABORES = ["Lavado de jabas", "Secado de jabas", "Limpieza de lámina burbupack"]
INCIDENCIAS = ["Falta de agua", "Falla de equipo", "Falta de energía", "Falta de jabas", "Falta de personal", "Limpieza del área", "Desperfecto mecánico", "Acumulación de jabas", "Otro"]

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

def now(): return datetime.now().isoformat(timespec="seconds")
def get(table, filters=None, order="id"):
    try:
        q = sb.table(table).select("*")
        for k, v in (filters or {}).items(): q = q.eq(k, v)
        if order: q = q.order(order, desc=True)
        return q.execute().data or []
    except Exception as e:
        message = getattr(e, "message", None) or str(e)
        st.error(f"Error de Supabase al consultar '{table}': {message}")
        return []
def frame(table, filters=None, order="id"): return pd.DataFrame(get(table, filters, order))
def add(table, data): return (sb.table(table).insert(data).execute().data or [None])[0]
def edit(table, data, filters):
    q = sb.table(table).update(data)
    for k, v in filters.items(): q = q.eq(k, v)
    return q.execute().data or []
def audit(tid, user, action, detail):
    add(T["audit"], {"turno_id": tid, "usuario": user, "accion": action, "detalle": detail, "fecha_hora": now()})
def mins(a, b):
    s, e = datetime.strptime(str(a)[:5], "%H:%M"), datetime.strptime(str(b)[:5], "%H:%M")
    if e <= s: e += timedelta(days=1)
    return int((e-s).total_seconds()/60)
def hours(a, b):
    m = mins(a, b)
    return max(m - (45 if m > 360 else 0), 0) / 60

def label(r): return f"#{int(r.id)} | {r.fecha} | {r.turno} | {r.asistente} | {r.estado}"
def choose_turn(statuses, user=None):
    d = frame(T["turnos"])
    if not d.empty: d = d[d.estado.isin(statuses)]
    if user and not d.empty: d = d[d.asistente == user]
    if d.empty: return None
    mp = {label(r): int(r.id) for _, r in d.iterrows()}
    return mp[st.selectbox("Turno", list(mp))]

st.sidebar.title("🧼 Lavado de jabas")
role = st.sidebar.selectbox("Ver como", ["ASISTENTE", "SUPERVISOR", "JEFATURA"])
users = frame(T["users"], order="nombre")
if role == "ASISTENTE":
    if not users.empty and "rol" in users: users = users[users.rol.astype(str).str.upper() == "ASISTENTE"]
    if not users.empty and "activo" in users: users = users[users.activo.astype(bool)]
    names = users.nombre.tolist() if not users.empty and "nombre" in users else []
    user = st.sidebar.selectbox("Asistente", names) if names else st.sidebar.text_input("Asistente", "Asistente piloto")
elif role == "SUPERVISOR": user = "Rafael Zapata"
else: user = "Jefatura de Logística"
menus = {
    "ASISTENTE": ["Inicio", "Abrir turno", "Operación", "Cerrar turno"],
    "SUPERVISOR": ["Panel", "Confirmar apertura", "Seguimiento", "Validar cierre"],
    "JEFATURA": ["Panel", "Turnos", "Incidencias", "Auditoría"],
}
page = st.sidebar.radio("Menú", menus[role])
st.sidebar.caption("Base central: Supabase")

if role == "ASISTENTE" and page == "Inicio":
    st.title("Piloto Lavado de Jabas")
    d = frame(T["turnos"], {"asistente": user})
    st.dataframe(d, use_container_width=True, hide_index=True) if not d.empty else st.info("Sin turnos registrados.")

elif role == "ASISTENTE" and page == "Abrir turno":
    st.title("Abrir turno")
    with st.form("open"):
        c1, c2 = st.columns(2); f = c1.date_input("Fecha", date.today()); shift = c2.selectbox("Turno", ["Día", "Noche"])
        defaults = {"Día": ("06:00", "18:00"), "Noche": ("18:00", "06:00")}
        c1, c2 = st.columns(2); hi = c1.time_input("Inicio", time.fromisoformat(defaults[shift][0])); hf = c2.time_input("Fin programado", time.fromisoformat(defaults[shift][1]))
        qty = [st.number_input(x, 0, 200, v) for x, v in zip(LABORES, [10, 4, 2])]
        obs = st.text_area("Observación")
        if st.form_submit_button("Enviar al supervisor", type="primary", use_container_width=True):
            try:
                row = add(T["turnos"], {"fecha": str(f), "turno": shift, "asistente": user, "hora_inicio": hi.strftime("%H:%M"), "hora_fin_programada": hf.strftime("%H:%M"), "estado": "Apertura enviada", "observacion_apertura": obs, "creado_en": now()})
                tid = row["id"]
                add(T["personal"], [{"turno_id": tid, "labor": lab, "personal_inicial": n, "personal_final": n, "hora_inicio": hi.strftime("%H:%M"), "hora_fin": None} for lab, n in zip(LABORES, qty)])
                audit(tid, user, "Apertura enviada", f"Personal inicial: {sum(qty)}")
                st.success(f"Turno #{tid} creado en Supabase.")
            except Exception as e: st.error(f"No se pudo crear el turno: {e}")

elif role == "ASISTENTE" and page == "Operación":
    st.title("Operación en curso"); tid = choose_turn(["En ejecución", "Observado"], user)
    if tid is None: st.info("No tienes turnos en ejecución.")
    else:
        a, b = st.tabs(["Incidencias", "Traslado interno"])
        with a:
            with st.form("inc"):
                typ = st.selectbox("Tipo", INCIDENCIAS); c1, c2 = st.columns(2); start = c1.time_input("Inicio", datetime.now().time().replace(second=0, microsecond=0)); close = c2.checkbox("Cerrar ahora")
                end = st.time_input("Fin", datetime.now().time().replace(second=0, microsecond=0), disabled=not close); desc = st.text_area("Descripción")
                if st.form_submit_button("Guardar"):
                    add(T["inc"], {"turno_id": tid, "tipo": typ, "hora_inicio": start.strftime("%H:%M"), "hora_fin": end.strftime("%H:%M") if close else None, "estado": "Cerrada" if close else "En curso", "afecta_produccion": True, "descripcion": desc, "creado_por": user, "creado_en": now()}); audit(tid, user, "Incidencia registrada", typ); st.rerun()
            st.dataframe(frame(T["inc"], {"turno_id": tid}), use_container_width=True, hide_index=True)
        with b:
            with st.form("move"):
                c1, c2 = st.columns(2); origin = c1.selectbox("Origen", LABORES); dest = c2.selectbox("Destino", LABORES, index=1); amount = st.number_input("Personas", 1, 200, 1); reason = st.text_input("Motivo")
                if st.form_submit_button("Registrar"):
                    if origin == dest: st.error("Origen y destino deben ser distintos.")
                    else: add(T["tras"], {"turno_id": tid, "hora": datetime.now().strftime("%H:%M"), "labor_origen": origin, "labor_destino": dest, "cantidad": amount, "motivo": reason, "creado_por": user, "creado_en": now()}); audit(tid, user, "Traslado interno", f"{amount}: {origin} → {dest}"); st.rerun()
            st.dataframe(frame(T["tras"], {"turno_id": tid}), use_container_width=True, hide_index=True)

elif role == "ASISTENTE" and page == "Cerrar turno":
    st.title("Cerrar turno"); tid = choose_turn(["En ejecución", "Observado"], user)
    if tid is None: st.info("No hay turnos disponibles.")
    else:
        p = frame(T["personal"], {"turno_id": tid}); t = frame(T["turnos"], {"id": tid}).iloc[0]
        with st.form("close"):
            vals = {int(r.id): st.number_input(r.labor, 0, 200, int(r.personal_final), key=f"p{r.id}") for _, r in p.iterrows()}
            end = st.time_input("Hora final real", time.fromisoformat(str(t.hora_fin_programada)[:5])); c1, c2, c3, c4 = st.columns(4)
            rec, lav, sec, lam = c1.number_input("Recibidas", 0.0), c2.number_input("Lavadas", 0.0), c3.number_input("Secadas", 0.0), c4.number_input("Láminas", 0.0)
            obs = st.text_area("Observación")
            if st.form_submit_button("Enviar cierre", type="primary"):
                for pid, n in vals.items(): edit(T["personal"], {"personal_final": n, "hora_fin": end.strftime("%H:%M")}, {"id": pid})
                payload = {"turno_id": tid, "jabas_recibidas": rec, "jabas_lavadas": lav, "jabas_secadas": sec, "laminas_limpiadas": lam, "observacion": obs, "enviado_por": user, "enviado_en": now(), "estado": "Pendiente"}
                if get(T["prod"], {"turno_id": tid}): edit(T["prod"], payload, {"turno_id": tid})
                else: add(T["prod"], payload)
                edit(T["turnos"], {"estado": "Cierre enviado"}, {"id": tid}); audit(tid, user, "Cierre enviado", f"Lavadas: {lav}"); st.success("Cierre enviado.")

elif role == "SUPERVISOR" and page == "Panel":
    st.title("Panel supervisor"); st.caption("Responsable: Rafael Zapata"); d = frame(T["turnos"])
    for col, status in zip(st.columns(4), ["Apertura enviada", "En ejecución", "Cierre enviado", "Validado"]): col.metric(status, int((d.estado == status).sum()) if not d.empty else 0)

elif role == "SUPERVISOR" and page == "Confirmar apertura":
    st.title("Confirmar apertura"); tid = choose_turn(["Apertura enviada"])
    if tid is None: st.info("No hay aperturas pendientes.")
    else:
        st.dataframe(frame(T["personal"], {"turno_id": tid}), use_container_width=True, hide_index=True)
        if st.button("Confirmar inicio", type="primary"): edit(T["turnos"], {"estado": "En ejecución", "confirmado_por": user, "confirmado_en": now()}, {"id": tid}); audit(tid, user, "Inicio confirmado", "Apertura validada"); st.rerun()

elif role == "SUPERVISOR" and page == "Seguimiento":
    st.title("Seguimiento"); tid = choose_turn(["En ejecución", "Cierre enviado", "Validado"])
    if tid is not None:
        for name, table in [("Incidencias", "inc"), ("Traslados", "tras"), ("Auditoría", "audit")]: st.subheader(name); st.dataframe(frame(T[table], {"turno_id": tid}), use_container_width=True, hide_index=True)

elif role == "SUPERVISOR" and page == "Validar cierre":
    st.title("Validar cierre"); tid = choose_turn(["Cierre enviado"])
    if tid is None: st.info("No hay cierres pendientes.")
    else:
        prod = frame(T["prod"], {"turno_id": tid}).iloc[0]; old = float(prod.jabas_lavadas)
        with st.form("validate"):
            new = st.number_input("Jabas lavadas", 0.0, value=old); reason = st.text_area("Motivo obligatorio si corrige")
            if st.form_submit_button("Validar", type="primary"):
                if new != old and not reason.strip(): st.error("Debe indicar el motivo.")
                else:
                    if new != old: edit(T["prod"], {"jabas_lavadas": new}, {"turno_id": tid}); audit(tid, user, "Corrección", f"{old} → {new}. {reason}")
                    edit(T["prod"], {"estado": "Validado", "validado_por": user, "validado_en": now()}, {"turno_id": tid}); edit(T["turnos"], {"estado": "Validado"}, {"id": tid}); audit(tid, user, "Cierre validado", "Validado por supervisor"); st.rerun()

elif role == "JEFATURA":
    st.title(page)
    table = {"Panel": "turnos", "Turnos": "turnos", "Incidencias": "inc", "Auditoría": "audit"}[page]
    d = frame(T[table]); st.dataframe(d, use_container_width=True, hide_index=True) if not d.empty else st.info("Sin datos.")

st.divider(); st.caption("Piloto Lavado de Jabas · Supabase · Refrigerio automático: 45 min en jornadas mayores a 6 horas")

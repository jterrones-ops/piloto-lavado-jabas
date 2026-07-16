
import sqlite3
from datetime import datetime, date, time, timedelta
from pathlib import Path
import pandas as pd
import streamlit as st

APP_DIR = Path(__file__).resolve().parent
DB = APP_DIR / "piloto_lavado.db"

st.set_page_config(
    page_title="Piloto Lavado de Jabas",
    page_icon="🧼",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
.block-container {padding-top: 1rem; padding-bottom: 2rem;}
[data-testid="stMetricValue"] {font-size: 1.45rem;}
.card {border:1px solid #e5e7eb;border-radius:14px;padding:14px;margin-bottom:10px;background:white;}
.ok {background:#ecfdf5;border-left:5px solid #10b981;padding:10px;border-radius:8px;}
.warn {background:#fff7ed;border-left:5px solid #f97316;padding:10px;border-radius:8px;}
.info {background:#eff6ff;border-left:5px solid #3b82f6;padding:10px;border-radius:8px;}
.small {font-size:.82rem;color:#6b7280;}
</style>
""", unsafe_allow_html=True)

def conn():
    c = sqlite3.connect(DB, check_same_thread=False)
    c.execute("PRAGMA foreign_keys=ON")
    return c

def init():
    c = conn()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS asistentes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        activo INTEGER NOT NULL DEFAULT 1,
        turno TEXT DEFAULT '',
        creado_en TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS turnos(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT NOT NULL,
        turno TEXT NOT NULL,
        asistente TEXT NOT NULL,
        hora_inicio TEXT NOT NULL,
        hora_fin_programada TEXT NOT NULL,
        estado TEXT NOT NULL DEFAULT 'Borrador',
        confirmado_por TEXT DEFAULT '',
        confirmado_en TEXT DEFAULT '',
        observacion_apertura TEXT DEFAULT '',
        creado_en TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS labores(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        turno_id INTEGER NOT NULL,
        labor TEXT NOT NULL,
        personal_inicial INTEGER NOT NULL DEFAULT 0,
        personal_final INTEGER NOT NULL DEFAULT 0,
        hora_inicio TEXT NOT NULL,
        hora_fin TEXT DEFAULT '',
        jabas_procesadas REAL NOT NULL DEFAULT 0,
        observacion TEXT DEFAULT '',
        FOREIGN KEY(turno_id) REFERENCES turnos(id)
    );
    CREATE TABLE IF NOT EXISTS incidencias(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        turno_id INTEGER NOT NULL,
        tipo TEXT NOT NULL,
        hora_inicio TEXT NOT NULL,
        hora_fin TEXT DEFAULT '',
        estado TEXT NOT NULL DEFAULT 'En curso',
        afecta_produccion INTEGER NOT NULL DEFAULT 1,
        descripcion TEXT DEFAULT '',
        creado_por TEXT NOT NULL,
        creado_en TEXT NOT NULL,
        FOREIGN KEY(turno_id) REFERENCES turnos(id)
    );
    CREATE TABLE IF NOT EXISTS traslados(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        turno_id INTEGER NOT NULL,
        hora TEXT NOT NULL,
        labor_origen TEXT NOT NULL,
        labor_destino TEXT NOT NULL,
        cantidad INTEGER NOT NULL,
        motivo TEXT DEFAULT '',
        creado_por TEXT NOT NULL,
        creado_en TEXT NOT NULL,
        FOREIGN KEY(turno_id) REFERENCES turnos(id)
    );
    CREATE TABLE IF NOT EXISTS cierres(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        turno_id INTEGER NOT NULL UNIQUE,
        jabas_recibidas REAL DEFAULT 0,
        jabas_lavadas REAL DEFAULT 0,
        jabas_secadas REAL DEFAULT 0,
        laminas_limpiadas REAL DEFAULT 0,
        observacion TEXT DEFAULT '',
        enviado_por TEXT NOT NULL,
        enviado_en TEXT NOT NULL,
        validado_por TEXT DEFAULT '',
        validado_en TEXT DEFAULT '',
        estado TEXT NOT NULL DEFAULT 'Pendiente',
        FOREIGN KEY(turno_id) REFERENCES turnos(id)
    );
    CREATE TABLE IF NOT EXISTS historial(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        turno_id INTEGER NOT NULL,
        usuario TEXT NOT NULL,
        accion TEXT NOT NULL,
        detalle TEXT NOT NULL,
        fecha_hora TEXT NOT NULL
    );
    """)
    if c.execute("SELECT COUNT(*) FROM asistentes").fetchone()[0] == 0:
        now = datetime.now().isoformat(timespec="seconds")
        c.executemany("INSERT INTO asistentes(nombre,activo,turno,creado_en) VALUES(?,?,?,?)", [
            ("Asistente Turno Mañana",1,"Mañana",now),
            ("Asistente Turno Noche",1,"Noche",now),
        ])
    c.commit()
    c.close()

def q(sql, p=()):
    c = conn()
    df = pd.read_sql_query(sql, c, params=p)
    c.close()
    return df

def ex(sql, p=()):
    c = conn()
    c.execute(sql, p)
    c.commit()
    c.close()

def dt_minutes(start_s, end_s):
    try:
        s = datetime.strptime(start_s, "%H:%M")
        e = datetime.strptime(end_s, "%H:%M")
        if e <= s:
            e += timedelta(days=1)
        return int((e-s).total_seconds()/60)
    except:
        return 0

def effective_hours(start_s, end_s, discount=True):
    mins = dt_minutes(start_s, end_s)
    if discount and mins > 360:
        mins -= 45
    return max(mins,0)/60

def duration_text(minutes):
    h, m = divmod(int(minutes), 60)
    return f"{h} h {m:02d} min"

def add_history(turno_id, usuario, accion, detalle):
    ex("INSERT INTO historial(turno_id,usuario,accion,detalle,fecha_hora) VALUES(?,?,?,?,?)",
       (turno_id, usuario, accion, detalle, datetime.now().isoformat(timespec="seconds")))

init()

st.sidebar.title("🧼 Lavado de jabas")
st.sidebar.caption("Piloto operativo")
perfil = st.sidebar.selectbox("Ver aplicación como", ["Asistente", "Supervisor", "Jefatura"])
if perfil == "Asistente":
    usuario = st.sidebar.selectbox("Usuario", q("SELECT nombre FROM asistentes WHERE activo=1")["nombre"].tolist())
elif perfil == "Supervisor":
    usuario = "Rafael Zapata"
else:
    usuario = "Jefatura de Logística"

st.sidebar.divider()
menu_opts = {
    "Asistente":["Mi inicio","Abrir turno","Operación en curso","Cerrar turno","Mis registros"],
    "Supervisor":["Panel supervisor","Validar apertura","Seguimiento","Validar cierre","Asistentes"],
    "Jefatura":["Panel jefatura","Turnos y productividad","Incidencias","Historial","Configuración"]
}
pagina = st.sidebar.radio("Menú", menu_opts[perfil])
st.sidebar.caption("Los datos se guardan en la base local del prototipo.")

turnos = q("SELECT * FROM turnos ORDER BY fecha DESC, id DESC")

def active_turn_options(statuses=None):
    sql = "SELECT id, fecha, turno, asistente, estado FROM turnos"
    params=[]
    if statuses:
        marks=",".join(["?"]*len(statuses))
        sql += f" WHERE estado IN ({marks})"
        params=statuses
    sql += " ORDER BY fecha DESC,id DESC"
    df=q(sql,params)
    return df

def turno_label(row):
    return f"#{int(row.id)} | {row.fecha} | {row.turno} | {row.asistente} | {row.estado}"

if perfil == "Asistente" and pagina == "Mi inicio":
    st.title("Lavado de jabas")
    st.caption(f"Usuario: {usuario}")
    mine = q("SELECT * FROM turnos WHERE asistente=? ORDER BY fecha DESC,id DESC", (usuario,))
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Borradores", int((mine["estado"]=="Borrador").sum()) if not mine.empty else 0)
    c2.metric("Esperando inicio", int((mine["estado"]=="Apertura enviada").sum()) if not mine.empty else 0)
    c3.metric("En ejecución", int((mine["estado"]=="En ejecución").sum()) if not mine.empty else 0)
    c4.metric("Observados", int((mine["estado"]=="Observado").sum()) if not mine.empty else 0)
    st.markdown('<div class="info">El asistente abre el turno, registra incidencias y traslados, y envía el cierre. El supervisor confirma y valida.</div>', unsafe_allow_html=True)
    if not mine.empty:
        st.dataframe(mine[["fecha","turno","hora_inicio","hora_fin_programada","estado"]],
                     use_container_width=True, hide_index=True)

elif perfil == "Asistente" and pagina == "Abrir turno":
    st.title("Apertura del turno")
    with st.form("apertura", clear_on_submit=True):
        c1,c2=st.columns(2)
        fecha=c1.date_input("Fecha", date.today())
        turno=c2.selectbox("Turno", ["Mañana","Noche"])
        defaults={"Mañana":("06:00","18:00"),"Noche":("18:00","06:00")}
        c3,c4=st.columns(2)
        hi=c3.time_input("Hora de inicio", time.fromisoformat(defaults[turno][0]))
        hf=c4.time_input("Hora final programada", time.fromisoformat(defaults[turno][1]))
        st.markdown("#### Personal inicial por labor")
        p1=st.number_input("Lavado de jabas",0,200,10)
        p2=st.number_input("Secado de jabas",0,200,4)
        p3=st.number_input("Limpieza de lámina burbupack",0,200,2)
        obs=st.text_area("Observación de apertura")
        guardar=st.form_submit_button("Enviar apertura al supervisor", type="primary", use_container_width=True)
        if guardar:
            now=datetime.now().isoformat(timespec="seconds")
            c=conn()
            cur=c.execute("""INSERT INTO turnos(fecha,turno,asistente,hora_inicio,hora_fin_programada,
                            estado,observacion_apertura,creado_en)
                            VALUES(?,?,?,?,?,'Apertura enviada',?,?)""",
                          (str(fecha),turno,usuario,hi.strftime("%H:%M"),hf.strftime("%H:%M"),obs,now))
            tid=cur.lastrowid
            rows=[
                (tid,"Lavado de jabas",p1,p1,hi.strftime("%H:%M"),""),
                (tid,"Secado de jabas",p2,p2,hi.strftime("%H:%M"),""),
                (tid,"Limpieza de lámina burbupack",p3,p3,hi.strftime("%H:%M"),""),
            ]
            c.executemany("""INSERT INTO labores(turno_id,labor,personal_inicial,personal_final,hora_inicio,hora_fin)
                             VALUES(?,?,?,?,?,?)""",rows)
            c.commit(); c.close()
            add_history(tid,usuario,"Apertura enviada",f"Turno {turno}, personal inicial: {p1+p2+p3}")
            st.success("Apertura enviada al supervisor.")
            st.rerun()

elif perfil == "Asistente" and pagina == "Operación en curso":
    st.title("Operación en curso")
    df=active_turn_options(["En ejecución","Observado"])
    df=df[df["asistente"]==usuario] if not df.empty else df
    if df.empty:
        st.info("No tienes turnos en ejecución.")
    else:
        mapping={turno_label(r):int(r.id) for _,r in df.iterrows()}
        sel=st.selectbox("Turno", list(mapping))
        tid=mapping[sel]
        tabs=st.tabs(["Incidencias","Traslado interno","Avance"])
        with tabs[0]:
            st.subheader("Registrar incidencia")
            tipos=["Falta de agua","Falla de equipo","Falta de energía","Falta de jabas",
                   "Falta de personal","Limpieza del área","Desperfecto mecánico",
                   "Acumulación de jabas","Otro"]
            with st.form("inc"):
                tipo=st.selectbox("Tipo",tipos)
                c1,c2=st.columns(2)
                ini=c1.time_input("Hora de inicio",value=datetime.now().time().replace(second=0,microsecond=0))
                cerrar=c2.checkbox("Registrar hora final ahora")
                fin=st.time_input("Hora final",value=datetime.now().time().replace(second=0,microsecond=0),disabled=not cerrar)
                afecta=st.checkbox("Afectó la producción",True)
                desc=st.text_area("Descripción")
                ok=st.form_submit_button("Guardar incidencia",type="primary",use_container_width=True)
                if ok:
                    estado="Cerrada" if cerrar else "En curso"
                    fin_s=fin.strftime("%H:%M") if cerrar else ""
                    ex("""INSERT INTO incidencias(turno_id,tipo,hora_inicio,hora_fin,estado,afecta_produccion,
                         descripcion,creado_por,creado_en) VALUES(?,?,?,?,?,?,?,?,?)""",
                       (tid,tipo,ini.strftime("%H:%M"),fin_s,estado,int(afecta),desc,usuario,
                        datetime.now().isoformat(timespec="seconds")))
                    add_history(tid,usuario,"Incidencia registrada",f"{tipo} desde {ini.strftime('%H:%M')}")
                    st.success("Incidencia guardada.")
                    st.rerun()
            inc=q("SELECT * FROM incidencias WHERE turno_id=? ORDER BY id DESC",(tid,))
            if not inc.empty:
                st.dataframe(inc[["tipo","hora_inicio","hora_fin","estado","descripcion"]],
                             use_container_width=True,hide_index=True)
                abiertas=inc[inc["estado"]=="En curso"]
                if not abiertas.empty:
                    st.markdown("#### Cerrar incidencia")
                    iid=st.selectbox("Incidencia abierta",abiertas["id"].tolist())
                    hf=st.time_input("Hora de solución",value=datetime.now().time().replace(second=0,microsecond=0))
                    if st.button("Cerrar incidencia",use_container_width=True):
                        ex("UPDATE incidencias SET hora_fin=?,estado='Cerrada' WHERE id=?",(hf.strftime("%H:%M"),int(iid)))
                        add_history(tid,usuario,"Incidencia cerrada",f"Incidencia #{iid} cerrada a {hf.strftime('%H:%M')}")
                        st.rerun()
        with tabs[1]:
            st.subheader("Traslado interno")
            labores=["Lavado de jabas","Secado de jabas","Limpieza de lámina burbupack"]
            with st.form("tras"):
                c1,c2=st.columns(2)
                origen=c1.selectbox("Desde labor",labores)
                destino=c2.selectbox("Hacia labor",labores,index=1)
                c3,c4=st.columns(2)
                hora_t=c3.time_input("Hora del traslado",value=datetime.now().time().replace(second=0,microsecond=0))
                cant=c4.number_input("Cantidad de personal",1,200,1)
                mot=st.text_input("Motivo")
                ok=st.form_submit_button("Registrar traslado",type="primary",use_container_width=True)
                if ok:
                    ex("""INSERT INTO traslados(turno_id,hora,labor_origen,labor_destino,cantidad,motivo,creado_por,creado_en)
                          VALUES(?,?,?,?,?,?,?,?)""",
                       (tid,hora_t.strftime("%H:%M"),origen,destino,cant,mot,usuario,
                        datetime.now().isoformat(timespec="seconds")))
                    add_history(tid,usuario,"Traslado interno",f"{cant} personas: {origen} → {destino}")
                    st.success("Traslado registrado.")
                    st.rerun()
            tr=q("SELECT * FROM traslados WHERE turno_id=? ORDER BY id DESC",(tid,))
            if not tr.empty:
                st.dataframe(tr[["hora","labor_origen","labor_destino","cantidad","motivo"]],
                             use_container_width=True,hide_index=True)
        with tabs[2]:
            st.subheader("Avance de producción")
            labs=q("SELECT * FROM labores WHERE turno_id=?",(tid,))
            for _,r in labs.iterrows():
                st.write(f"**{r['labor']}** — personal inicial: {int(r['personal_inicial'])}")
            st.caption("El resultado final se registra en el cierre. La productividad no es editable.")

elif perfil == "Asistente" and pagina == "Cerrar turno":
    st.title("Cierre del turno")
    df=active_turn_options(["En ejecución","Observado"])
    df=df[df["asistente"]==usuario] if not df.empty else df
    if df.empty:
        st.info("No tienes turnos disponibles para cierre.")
    else:
        mapping={turno_label(r):int(r.id) for _,r in df.iterrows()}
        sel=st.selectbox("Turno",list(mapping)); tid=mapping[sel]
        trow=q("SELECT * FROM turnos WHERE id=?",(tid,)).iloc[0]
        labs=q("SELECT * FROM labores WHERE turno_id=?",(tid,))
        with st.form("cierre"):
            st.markdown("#### Personal real al cierre")
            vals={}
            for _,r in labs.iterrows():
                vals[int(r["id"])]=st.number_input(r["labor"],0,200,int(r["personal_final"]),key=f"p{r['id']}")
            hf=st.time_input("Hora final real",value=time.fromisoformat(trow["hora_fin_programada"]))
            c1,c2,c3,c4=st.columns(4)
            recibidas=c1.number_input("Jabas recibidas",0.0,1000000.0,0.0,step=100.0)
            lavadas=c2.number_input("Jabas lavadas",0.0,1000000.0,0.0,step=100.0)
            secadas=c3.number_input("Jabas secadas",0.0,1000000.0,0.0,step=100.0)
            laminas=c4.number_input("Láminas limpiadas",0.0,1000000.0,0.0,step=10.0)
            obs=st.text_area("Observación de cierre")
            ok=st.form_submit_button("Enviar cierre al supervisor",type="primary",use_container_width=True)
            if ok:
                for lid,pv in vals.items():
                    ex("UPDATE labores SET personal_final=?,hora_fin=? WHERE id=?",(pv,hf.strftime("%H:%M"),lid))
                existing=q("SELECT id FROM cierres WHERE turno_id=?",(tid,))
                if existing.empty:
                    ex("""INSERT INTO cierres(turno_id,jabas_recibidas,jabas_lavadas,jabas_secadas,
                       laminas_limpiadas,observacion,enviado_por,enviado_en,estado)
                       VALUES(?,?,?,?,?,?,?,?, 'Pendiente')""",
                       (tid,recibidas,lavadas,secadas,laminas,obs,usuario,
                        datetime.now().isoformat(timespec="seconds")))
                else:
                    ex("""UPDATE cierres SET jabas_recibidas=?,jabas_lavadas=?,jabas_secadas=?,
                       laminas_limpiadas=?,observacion=?,enviado_por=?,enviado_en=?,estado='Pendiente'
                       WHERE turno_id=?""",
                       (recibidas,lavadas,secadas,laminas,obs,usuario,
                        datetime.now().isoformat(timespec="seconds"),tid))
                ex("UPDATE turnos SET estado='Cierre enviado' WHERE id=?",(tid,))
                add_history(tid,usuario,"Cierre enviado",f"Jabas lavadas: {lavadas}")
                st.success("Cierre enviado al supervisor.")
                st.rerun()

elif perfil == "Asistente" and pagina == "Mis registros":
    st.title("Mis registros")
    mine=q("SELECT * FROM turnos WHERE asistente=? ORDER BY fecha DESC,id DESC",(usuario,))
    st.dataframe(mine,use_container_width=True,hide_index=True)

elif perfil == "Supervisor" and pagina == "Panel supervisor":
    st.title("Panel del supervisor")
    st.caption("Responsable: Rafael Zapata")
    all_t=q("SELECT * FROM turnos ORDER BY fecha DESC,id DESC")
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Aperturas pendientes",int((all_t["estado"]=="Apertura enviada").sum()) if not all_t.empty else 0)
    c2.metric("En ejecución",int((all_t["estado"]=="En ejecución").sum()) if not all_t.empty else 0)
    c3.metric("Cierres pendientes",int((all_t["estado"]=="Cierre enviado").sum()) if not all_t.empty else 0)
    c4.metric("Validados",int((all_t["estado"]=="Validado").sum()) if not all_t.empty else 0)
    st.markdown('<div class="warn">La productividad no se edita. Si se corrige personal, horario o producción, el sistema exige motivo y guarda historial.</div>',unsafe_allow_html=True)

elif perfil == "Supervisor" and pagina == "Validar apertura":
    st.title("Validar apertura")
    df=active_turn_options(["Apertura enviada"])
    if df.empty:
        st.info("No hay aperturas pendientes.")
    else:
        mapping={turno_label(r):int(r.id) for _,r in df.iterrows()}
        sel=st.selectbox("Selecciona",list(mapping)); tid=mapping[sel]
        t=q("SELECT * FROM turnos WHERE id=?",(tid,)).iloc[0]
        labs=q("SELECT * FROM labores WHERE turno_id=?",(tid,))
        st.write(f"**Asistente:** {t['asistente']}  \n**Horario:** {t['hora_inicio']}–{t['hora_fin_programada']}")
        st.dataframe(labs[["labor","personal_inicial","hora_inicio"]],use_container_width=True,hide_index=True)
        c1,c2=st.columns(2)
        if c1.button("Confirmar inicio",type="primary",use_container_width=True):
            ex("""UPDATE turnos SET estado='En ejecución',confirmado_por=?,confirmado_en=? WHERE id=?""",
               (usuario,datetime.now().isoformat(timespec="seconds"),tid))
            add_history(tid,usuario,"Inicio confirmado","Apertura validada por supervisor")
            st.rerun()
        if c2.button("Observar apertura",use_container_width=True):
            ex("UPDATE turnos SET estado='Observado' WHERE id=?",(tid,))
            add_history(tid,usuario,"Apertura observada","Devuelta al asistente")
            st.rerun()

elif perfil == "Supervisor" and pagina == "Seguimiento":
    st.title("Seguimiento operativo")
    df=active_turn_options(["En ejecución","Cierre enviado","Validado"])
    if df.empty:
        st.info("No hay turnos.")
    else:
        mapping={turno_label(r):int(r.id) for _,r in df.iterrows()}
        sel=st.selectbox("Turno",list(mapping)); tid=mapping[sel]
        inc=q("SELECT * FROM incidencias WHERE turno_id=? ORDER BY id DESC",(tid,))
        tr=q("SELECT * FROM traslados WHERE turno_id=? ORDER BY id DESC",(tid,))
        tabs=st.tabs(["Incidencias","Traslados","Historial"])
        with tabs[0]:
            st.dataframe(inc,use_container_width=True,hide_index=True) if not inc.empty else st.info("Sin incidencias.")
        with tabs[1]:
            st.dataframe(tr,use_container_width=True,hide_index=True) if not tr.empty else st.info("Sin traslados.")
        with tabs[2]:
            hist=q("SELECT usuario,accion,detalle,fecha_hora FROM historial WHERE turno_id=? ORDER BY id DESC",(tid,))
            st.dataframe(hist,use_container_width=True,hide_index=True)

elif perfil == "Supervisor" and pagina == "Validar cierre":
    st.title("Validar cierre")
    df=active_turn_options(["Cierre enviado"])
    if df.empty:
        st.info("No hay cierres pendientes.")
    else:
        mapping={turno_label(r):int(r.id) for _,r in df.iterrows()}
        sel=st.selectbox("Turno",list(mapping)); tid=mapping[sel]
        t=q("SELECT * FROM turnos WHERE id=?",(tid,)).iloc[0]
        labs=q("SELECT * FROM labores WHERE turno_id=?",(tid,))
        ci=q("SELECT * FROM cierres WHERE turno_id=?",(tid,)).iloc[0]
        total_hh=0
        for _,r in labs.iterrows():
            h=effective_hours(r["hora_inicio"],r["hora_fin"] or t["hora_fin_programada"])
            total_hh += h*float(r["personal_final"])
        prod=float(ci["jabas_lavadas"])/total_hh if total_hh else 0
        c1,c2,c3,c4=st.columns(4)
        c1.metric("Jabas lavadas",f"{ci['jabas_lavadas']:,.0f}")
        c2.metric("Horas-hombre",f"{total_hh:,.1f}")
        c3.metric("Productividad",f"{prod:,.2f} jabas/HH")
        inc=q("SELECT * FROM incidencias WHERE turno_id=?",(tid,))
        mins=0
        for _,r in inc.iterrows():
            if r["hora_fin"]:
                mins += dt_minutes(r["hora_inicio"],r["hora_fin"])
        c4.metric("Tiempo detenido",duration_text(mins))
        st.dataframe(labs[["labor","personal_inicial","personal_final","hora_inicio","hora_fin"]],
                     use_container_width=True,hide_index=True)
        st.markdown("#### Corrección justificada")
        with st.form("corr"):
            nuevo=st.number_input("Jabas lavadas corregidas",0.0,1000000.0,float(ci["jabas_lavadas"]),step=100.0)
            motivo=st.text_area("Motivo obligatorio si cambia el valor")
            validar=st.form_submit_button("Validar cierre",type="primary",use_container_width=True)
            if validar:
                if nuevo != float(ci["jabas_lavadas"]) and not motivo.strip():
                    st.error("Debes indicar el motivo de la corrección.")
                else:
                    if nuevo != float(ci["jabas_lavadas"]):
                        old=float(ci["jabas_lavadas"])
                        ex("UPDATE cierres SET jabas_lavadas=? WHERE turno_id=?",(nuevo,tid))
                        add_history(tid,usuario,"Corrección de cierre",f"Jabas lavadas: {old} → {nuevo}. Motivo: {motivo}")
                    ex("""UPDATE cierres SET estado='Validado',validado_por=?,validado_en=? WHERE turno_id=?""",
                       (usuario,datetime.now().isoformat(timespec="seconds"),tid))
                    ex("UPDATE turnos SET estado='Validado' WHERE id=?",(tid,))
                    add_history(tid,usuario,"Cierre validado","Registro validado por supervisor")
                    st.success("Cierre validado.")
                    st.rerun()

elif perfil == "Supervisor" and pagina == "Asistentes":
    st.title("Asistentes de la operación")
    asis=q("SELECT * FROM asistentes ORDER BY activo DESC,nombre")
    st.dataframe(asis[["nombre","turno","activo"]],use_container_width=True,hide_index=True)
    st.caption("La creación y actualización definitiva la controla Jefatura.")

elif perfil == "Jefatura" and pagina == "Panel jefatura":
    st.title("Panel de jefatura — Lavado de jabas")
    vals=q("""SELECT t.fecha,t.turno,t.asistente,t.estado,c.jabas_lavadas,c.jabas_secadas,
              c.laminas_limpiadas FROM turnos t LEFT JOIN cierres c ON c.turno_id=t.id
              ORDER BY t.fecha DESC,t.id DESC""")
    val=vals[vals["estado"]=="Validado"] if not vals.empty else vals
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Turnos validados",len(val))
    c2.metric("Jabas lavadas",f"{val['jabas_lavadas'].fillna(0).sum():,.0f}" if not val.empty else "0")
    c3.metric("Jabas secadas",f"{val['jabas_secadas'].fillna(0).sum():,.0f}" if not val.empty else "0")
    inc=q("SELECT * FROM incidencias")
    c4.metric("Incidencias",len(inc))
    if not vals.empty:
        st.dataframe(vals,use_container_width=True,hide_index=True)

elif perfil == "Jefatura" and pagina == "Turnos y productividad":
    st.title("Turnos y productividad")
    ts=q("""SELECT t.id,t.fecha,t.turno,t.asistente,t.hora_inicio,t.hora_fin_programada,t.estado,
            c.jabas_lavadas,c.jabas_secadas FROM turnos t
            LEFT JOIN cierres c ON c.turno_id=t.id ORDER BY t.fecha DESC,t.id DESC""")
    out=[]
    for _,r in ts.iterrows():
        labs=q("SELECT * FROM labores WHERE turno_id=?",(int(r["id"]),))
        hh=0
        for _,l in labs.iterrows():
            end=l["hora_fin"] or r["hora_fin_programada"]
            hh += effective_hours(l["hora_inicio"],end)*float(l["personal_final"])
        lav=float(r["jabas_lavadas"] or 0)
        out.append({**r.to_dict(),"horas_hombre":hh,"productividad":lav/hh if hh else 0})
    if out:
        df=pd.DataFrame(out)
        st.dataframe(df,use_container_width=True,hide_index=True)
        csv=df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("Descargar reporte CSV",csv,"lavado_jabas_productividad.csv","text/csv",use_container_width=True)
    else:
        st.info("Sin datos.")

elif perfil == "Jefatura" and pagina == "Incidencias":
    st.title("Incidencias")
    inc=q("""SELECT i.*,t.fecha,t.turno,t.asistente FROM incidencias i
             JOIN turnos t ON t.id=i.turno_id ORDER BY t.fecha DESC,i.id DESC""")
    st.dataframe(inc,use_container_width=True,hide_index=True) if not inc.empty else st.info("Sin incidencias.")

elif perfil == "Jefatura" and pagina == "Historial":
    st.title("Historial de cambios")
    h=q("""SELECT h.*,t.fecha,t.turno,t.asistente FROM historial h
           JOIN turnos t ON t.id=h.turno_id ORDER BY h.id DESC""")
    st.dataframe(h,use_container_width=True,hide_index=True) if not h.empty else st.info("Sin historial.")

elif perfil == "Jefatura" and pagina == "Configuración":
    st.title("Configuración")
    tabs=st.tabs(["Asistentes","Turnos"])
    with tabs[0]:
        st.subheader("Actualizar asistentes")
        asis=q("SELECT * FROM asistentes ORDER BY activo DESC,nombre")
        st.dataframe(asis[["id","nombre","turno","activo"]],use_container_width=True,hide_index=True)
        with st.form("nuevoasis"):
            nombre=st.text_input("Nombre del asistente")
            turno=st.selectbox("Turno asignado",["Mañana","Noche","Ambos"])
            ok=st.form_submit_button("Agregar asistente",type="primary",use_container_width=True)
            if ok and nombre.strip():
                ex("INSERT INTO asistentes(nombre,activo,turno,creado_en) VALUES(?,1,?,?)",
                   (nombre.strip(),turno,datetime.now().isoformat(timespec="seconds")))
                st.success("Asistente agregado.")
                st.rerun()
        if not asis.empty:
            aid=st.selectbox("Asistente a actualizar",asis["id"].tolist())
            row=asis[asis["id"]==aid].iloc[0]
            nuevo=st.text_input("Nuevo nombre",value=row["nombre"])
            activo=st.checkbox("Activo",value=bool(row["activo"]))
            turno2=st.selectbox("Turno",["Mañana","Noche","Ambos"],index=["Mañana","Noche","Ambos"].index(row["turno"]) if row["turno"] in ["Mañana","Noche","Ambos"] else 0)
            if st.button("Guardar actualización",use_container_width=True):
                ex("UPDATE asistentes SET nombre=?,activo=?,turno=? WHERE id=?",(nuevo.strip(),int(activo),turno2,int(aid)))
                st.success("Asistente actualizado.")
                st.rerun()
    with tabs[1]:
        st.write("**Turno mañana:** 06:00–18:00")
        st.write("**Turno noche:** 18:00–06:00")
        st.write("**Refrigerio automático:** 45 minutos cuando la jornada supera 6 horas")

st.divider()
st.caption("Prototipo funcional del piloto Operación 1. Para pruebas, cambia el perfil en el menú lateral.")

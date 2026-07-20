begin;

alter table public.personal_labor
    drop constraint if exists personal_labor_labor_check;

alter table public.personal_labor
    add constraint personal_labor_labor_check
    check (
        labor in (
            'Lavado',
            'Secado',
            'Limpieza de lámina burbupack',
            'Carga',
            'Distribución',
            'Recojo',
            'Colocación de hilo nylon',
            'Colocación de lámina',
            'Colocación de burbupack',
            'Estiba',
            'Desestiba en puntos de cosecha',
            'Lote → Acopio',
            'Acopio → Packing',
            'Asistente (acopiador)',
            'Estibadores',
            'Montacarguistas'
        )
    );

commit;

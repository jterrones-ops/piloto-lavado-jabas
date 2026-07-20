begin;

alter table public.personal_labor
    drop constraint if exists personal_labor_labor_check;

update public.personal_labor
set labor = 'Sin especificar'
where labor is null or btrim(labor) = '';

alter table public.personal_labor
    add constraint personal_labor_labor_check
    check (labor is not null and btrim(labor) <> '');

commit;

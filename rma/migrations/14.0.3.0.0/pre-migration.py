
def migrate(cr, version):
    module = 'rma'
    model = 'rma.operation'
    table = model.replace('.', '_')

    for xmlid, name in [
        ('rma_operation_replace', 'Replace'),
        ('rma_operation_return', 'Return'),
        ('rma_operation_refund', 'Refund'),
        ('rma_operation_repair', 'Repair'),
    ]:
        cr.execute(f"select id from {table} where name = '{name}'")
        res = cr.fetchall()
        if not res:
            continue

        res_id = res[0][0]
        
        cr.execute(f"""
        select
            id
        from
            ir_model_data
        where
            module = '{module}'
        and
            name = '{xmlid}';
        """)

        res = cr.fetchall()
        if not res:
            cr.execute(f"""
            Insert into ir_model_data
                (
                    module,
                    model,
                    name,
                    res_id,
                    noupdate,
                    create_date,
                    write_date
                )
            Values
                (
                    '{module}',
                    '{model}',
                    '{xmlid}',
                    {res_id},
                    true,
                    now(),
                    now()
                );
            """)
        else:
            cr.execute(f"""
            Update
                ir_model_data
            set
                res_id = '{res_id}'
            where
                id = {res[0][0]}
            """)

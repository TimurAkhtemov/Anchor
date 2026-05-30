with payments as ( 
    select 
        order_id,
        sum(amount) as amount
    from {{ ref('stg_stripe__payments') }}
    where status = 'success'
    group by order_id
),

orders as ( 
    select * from {{ ref('stg_jaffle_shop__orders') }}
),

final as (
    select 
        orders.order_id,
        orders.customer_id,
        payments.amount
    from orders
    left join payments
        on orders.order_id = payments.order_id
)

select * from final

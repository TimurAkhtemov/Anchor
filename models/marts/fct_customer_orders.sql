with

    -- Import CTEs
    customers as (select * from {{ source("jaffle_shop", "customers") }}),

    orders as (select * from {{ source("jaffle_shop", "orders") }}),

    payments as (select * from {{ source("stripe", "payment") }}),
    
    -- Logical CTEs
    p as (
        select
            orderid as order_id,
            max(created) as payment_finalized_date,
            sum(amount) / 100.0 as total_amount_paid
        from payments
        where status <> 'fail'
        group by 1
    ),

    paid_orders as (
        select
            orders.id as order_id,
            orders.user_id as customer_id,
            orders.order_date as order_placed_at,
            orders.status as order_status,
            p.total_amount_paid,
            p.payment_finalized_date,
            c.first_name as customer_first_name,
            c.last_name as customer_last_name
        from orders
        left join p on orders.id = p.order_id
        left join customers c on orders.user_id = c.id
    ),

    final as (
        select
            paid_orders.order_id,
            paid_orders.customer_id,
            paid_orders.order_placed_at,
            paid_orders.order_status,
            paid_orders.total_amount_paid,
            paid_orders.payment_finalized_date,
            paid_orders.customer_first_name,
            paid_orders.customer_last_name,

            -- sales sequence
            row_number() over (order by paid_orders.order_id) as transaction_seq,

            row_number() over (
                partition by paid_orders.customer_id 
                order by paid_orders.order_id
            ) as customer_sales_seq,

            -- new vs returning customer
            case
                when (
                    rank() over (
                        partition by paid_orders.customer_id
                        order by paid_orders.order_placed_at, paid_orders.order_id
                    ) = 1
                ) then 'new'
                else 'return'
            end as nvsr,

            -- customer lifetime value
            sum(paid_orders.total_amount_paid) over (
                partition by paid_orders.customer_id
                order by paid_orders.order_placed_at, paid_orders.order_id
            ) as customer_lifetime_value,

            -- first date of sale
            first_value(paid_orders.order_placed_at) over (
                partition by paid_orders.customer_id
                order by paid_orders.order_placed_at, paid_orders.order_id
            ) as fdos

        from paid_orders
    )

select *
from final
order by order_id


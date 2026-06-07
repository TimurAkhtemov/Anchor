{% docs order_status %}

Staging table for order status. Contains the current status of each order, including the status of each line item.

One of the following values: 

| status         | definition                                       |
|----------------|--------------------------------------------------|
| placed         | Order placed, not yet shipped                    |
| shipped        | Order has been shipped, not yet been delivered   |
| completed      | Order has been received by customers             |
| return pending | Customer indicated they want to return this item |
| returned       | Item has been returned                           |

{% enddocs %}

{% docs payment_method %}

The method of payment used for the transaction. 

One of the following values:

| payment_method | definition |
|----------------|------------|
| credit_card    | Payment made via credit card |
| coupon         | Payment made using a promotional coupon |
| bank_transfer  | Direct bank transfer |
| gift_card      | Payment made using a gift card |

{% enddocs %}

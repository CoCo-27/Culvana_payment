# check_payment_status/__init__.py
import azure.functions as func
import json
import logging
from shared_code.db_client import CosmosDBClient
from datetime import datetime, timezone

def main(req: func.HttpRequest) -> func.HttpResponse:
    db_client = CosmosDBClient()
    
    try:
        req_body = req.get_json()
        email = req_body.get('email')
        
        payment_setup = db_client.get_payment_setup(email)
        if not payment_setup:
            return func.HttpResponse(
                json.dumps({"error": "No payment setup found"}),
                mimetype="application/json",
                status_code=404
            )

        # Check for pending transactions
        query = """
        SELECT * FROM c 
        WHERE c.type = 'transaction' 
        AND c.user_id = @user_id 
        AND c.transaction_type = 'weekly_billing'
        AND c.status = 'pending'
        """
        parameters = [{"name": "@user_id", "value": email}]
        
        pending_transactions = list(db_client.transaction_container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True
        ))

        if pending_transactions:
            # Calculate total pending amount
            total_pending = sum(t.get('amount', 0)/100 for t in pending_transactions)  # Convert cents to tokens
            current_tokens = payment_setup.get('tokens', 0)

            logging.info(f"Tokens: {current_tokens}, Pending: {total_pending}")

            if current_tokens >= total_pending:
                # User has enough tokens, process payment
                new_balance = current_tokens - total_pending
                
                # Update monthly usage
                current_monthly_usage = payment_setup.get('monthly_usage', 0)
                
                # Update payment setup
                updated_setup = db_client.create_payment_setup(
                    email=email,
                    status=payment_setup.get('status', 'active'),
                    tokens=new_balance,
                    stripe_customer_id=payment_setup.get('stripe_customer_id'),
                    plan_type=payment_setup.get('plan_type'),
                    custom_threshold=payment_setup.get('custom_threshold'),
                    num_locations=payment_setup.get('num_locations', 0),
                    pending_fee=0,  # Reset pending fee
                    monthly_usage=current_monthly_usage + total_pending
                )

                # Mark transactions as completed
                for transaction in pending_transactions:
                    transaction['status'] = 'completed'
                    transaction['completed_at'] = datetime.now(timezone.utc).isoformat()
                    db_client.transaction_container.replace_item(
                        item=transaction['id'],
                        body=transaction
                    )

                return func.HttpResponse(
                    json.dumps({
                        "status": "success",
                        "message": "Payment processed automatically",
                        "remaining_tokens": new_balance,
                        "monthly_usage": updated_setup['monthly_usage']
                    }),
                    mimetype="application/json",
                    status_code=200
                )

        # No pending transactions or not enough tokens
        return func.HttpResponse(
            json.dumps({
                "status": "success",
                "has_access": True,
                "data": payment_setup
            }),
            mimetype="application/json",
            status_code=200
        )

    except Exception as e:
        logging.error(f'Error: {str(e)}')
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            mimetype="application/json",
            status_code=500
        )
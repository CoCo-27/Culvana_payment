import azure.functions as func
import json
import logging
from shared_code.db_client import CosmosDBClient
from shared_code.middleware import check_payment_access

@check_payment_access
def main(req: func.HttpRequest) -> func.HttpResponse:
    db_client = CosmosDBClient()
    
    try:
        req_body = req.get_json()
        email = req_body.get('email')
        
        if not email:
            return func.HttpResponse(
                json.dumps({
                    "error": "Email parameter is required",
                    "error_code": "missing_email"
                }),
                mimetype="application/json",
                status_code=400
            )

        # Get payment setup from database
        payment_setup = db_client.get_payment_setup(email)
        
        if not payment_setup:
            return func.HttpResponse(
                json.dumps({
                    "error": "Payment setup not found",
                    "error_code": "not_found"
                }),
                mimetype="application/json",
                status_code=404
            )

        # Return payment information with safe get operations
        return func.HttpResponse(
            json.dumps({
                "status": "success",
                "data": {
                    "id": payment_setup.get('id'),
                    "email": payment_setup.get('email'),
                    "status": payment_setup.get('status'),
                    "tokens": payment_setup.get('tokens', 0),
                    "stripe_customer_id": payment_setup.get('stripe_customer_id'),
                    "plan_type": payment_setup.get('plan_type'),
                    "custom_threshold": payment_setup.get('custom_threshold'),
                    "num_locations": payment_setup.get('num_locations', 0),
                    "pending_fee": payment_setup.get('pending_fee', 0),
                    "monthly_usage": payment_setup.get('monthly_usage', 0),
                    "payment_methods": payment_setup.get('payment_methods', []),
                    "created_at": payment_setup.get('created_at'),
                    "updated_at": payment_setup.get('updated_at')
                }
            }),
            mimetype="application/json",
            status_code=200
        )
            
    except Exception as e:
        logging.error(f'Error getting payment info: {str(e)}')
        return func.HttpResponse(
            json.dumps({
                "error": "Failed to get payment information",
                "error_code": "server_error",
                "details": str(e)
            }),
            mimetype="application/json",
            status_code=500
        )
from functools import wraps
import json
import logging
import azure.functions as func
from .db_client import CosmosDBClient

def check_payment_access(func_to_wrap):
    @wraps(func_to_wrap)
    def wrapper(req: func.HttpRequest, *args, **kwargs):
        try:
            req_body = req.get_json()
            email = req_body.get('email')
            if not email:
                return func.HttpResponse(
                    json.dumps({
                        "error": "Email is required",
                        "error_code": "missing_email"
                    }),
                    mimetype="application/json",
                    status_code=400
                )
            db_client = CosmosDBClient()
            
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
                return func.HttpResponse(
                    json.dumps({
                        "error": "Payment required to access this feature",
                        "error_code": "payment_required",
                        "requires_subscription": True
                    }),
                    mimetype="application/json",
                    status_code=402
                )
            return func_to_wrap(req, *args, **kwargs)
        except Exception as e:
            logging.error(f'Error in payment middleware: {str(e)}')
            return func.HttpResponse(
                json.dumps({
                    "error": "An unexpected error occurred",
                    "error_code": "server_error"
                }),
                mimetype="application/json",
                status_code=500
            )
    return wrapper
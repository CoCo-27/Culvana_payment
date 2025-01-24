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

        payment_logs = db_client.get_payment_log(email)
        print("payment_log === ", payment_logs)
        
        if not payment_logs:
            return func.HttpResponse(
                json.dumps({
                    "error": "Payment logs not found",
                    "error_code": "not_found"
                }),
                mimetype="application/json",
                status_code=404
            )

        # Calculate summary statistics
        total_amount = sum(log.get('amount', 0) for log in payment_logs)
        total_tokens = sum(log.get('tokens_included', 0) for log in payment_logs)
        
        # Process payment logs
        processed_logs = []
        for log in payment_logs:
            processed_logs.append({
                "id": log.get('id'),
                "user_id": log.get('user_id'),
                "amount": log.get('amount', 0),
                "transaction_type": log.get('transaction_type'),
                "location_id": log.get('location_id'),
                "status": log.get('status'),
                "tokens_included": log.get('tokens_included', 0),
                "created_at": log.get('created_at'),
                "updated_at": log.get('updated_at')
            })

        return func.HttpResponse(
            json.dumps({
                "status": "success",
                "data": {
                    "summary": {
                        "total_amount": total_amount,
                        "total_tokens": total_tokens,
                        "transaction_count": len(processed_logs)
                    },
                    "transactions": processed_logs
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
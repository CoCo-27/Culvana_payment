# get_locations/__init__.py
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
                json.dumps({"error": "Email is required"}),
                mimetype="application/json",
                status_code=400
            )

        try:
            # Get all locations for the user
            locations = db_client.get_locations(email)
            
            # Get payment setup
            payment_setup = db_client.get_payment_setup(email)
            
            if not payment_setup:
                return func.HttpResponse(
                    json.dumps({"error": "No payment setup found for this email"}),
                    mimetype="application/json",
                    status_code=404
                )

            return func.HttpResponse(
                json.dumps({
                    'status': 'success',
                    'locations': locations,
                    'num_locations': payment_setup['num_locations'],
                    'pending_fee': payment_setup['pending_fee']
                }),
                mimetype="application/json",
                status_code=200
            )

        except Exception as e:
            logging.error(f'Database error: {str(e)}')
            return func.HttpResponse(
                json.dumps({
                    "error": "Failed to retrieve locations",
                    "error_code": "database_error"
                }),
                mimetype="application/json",
                status_code=400
            )

    except Exception as e:
        logging.error(f'Error: {str(e)}')
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            mimetype="application/json",
            status_code=500
        )
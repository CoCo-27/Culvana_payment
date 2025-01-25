# get_plan/__init__.py
import azure.functions as func
import json
import logging
from shared_code.db_client import CosmosDBClient
from shared_code.middleware import check_payment_access

@check_payment_access

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')
    db_client = CosmosDBClient()
    
    try:
        try:
            req_body = req.get_json()
            logging.info(f"Request body: {req_body}")
        except ValueError:
            logging.error("Invalid JSON in request body")
            return func.HttpResponse(
                json.dumps({
                    "error": "Invalid request body",
                    "error_code": "invalid_request"
                }),
                mimetype="application/json",
                status_code=400
            )

        email = req_body.get('email')
        logging.info(f"Processing request for email: {email}")
        
        if not email:
            logging.error("Email is missing in request")
            return func.HttpResponse(
                json.dumps({
                    "error": "Email is required",
                    "error_code": "missing_email"
                }),
                mimetype="application/json",
                status_code=400
            )

        try:
            payment_setup = db_client.get_payment_setup(email)
            logging.info(f"Payment setup retrieved: {payment_setup}")

            if not payment_setup:
                logging.warning(f"No payment setup found for email: {email}")
                return func.HttpResponse(
                    json.dumps({
                        "error": "No payment setup found for this email",
                        "error_code": "not_found"
                    }),
                    mimetype="application/json",
                    status_code=404
                )

            return func.HttpResponse(
                json.dumps({
                    "status": "success",
                    "updated_setup": payment_setup,
                    "num_locations": payment_setup.get('num_locations', 0),
                    "pending_fee": payment_setup.get('pending_fee', 0)
                }),
                mimetype="application/json",
                status_code=200
            )

        except Exception as e:
            logging.error(f'Database error: {str(e)}')
            return func.HttpResponse(
                json.dumps({
                    "error": "Failed to retrieve plan data",
                    "error_code": "database_error",
                    "details": str(e)
                }),
                mimetype="application/json",
                status_code=500
            )

    except Exception as e:
        logging.error(f'Unexpected error: {str(e)}')
        return func.HttpResponse(
            json.dumps({
                "error": str(e),
                "error_code": "server_error"
            }),
            mimetype="application/json",
            status_code=500
        )
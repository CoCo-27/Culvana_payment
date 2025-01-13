import azure.functions as func
import json
import logging
from shared_code.db_client import CosmosDBClient
from shared_code.middleware import check_payment_access
import stripe
from datetime import datetime

@check_payment_access
def main(req: func.HttpRequest) -> func.HttpResponse:
    db_client = CosmosDBClient()
    
    try:
        req_body = req.get_json()
        email = req_body.get('email')
        token = req_body.get('token')
        
        if not all([email, token]):
            return func.HttpResponse(
                json.dumps({
                    "error": "Email and token are required",
                    "error_code": "missing_fields"
                }),
                mimetype="application/json",
                status_code=400
            )

        try:
            # Get existing payment setup
            payment_setup = db_client.get_payment_setup(email)
            
            if not payment_setup:
                return func.HttpResponse(
                    json.dumps({
                        "error": "No payment setup found for this email",
                        "error_code": "not_found"
                    }),
                    mimetype="application/json",
                    status_code=404
                )

            # Add card to existing Stripe customer
            customer = stripe.Customer.retrieve(payment_setup['stripe_customer_id'])
            card = stripe.Customer.create_source(
                customer.id,
                source=token
            )

            # Update payment_methods array
            current_payment_methods = payment_setup.get('payment_methods', [])
            current_payment_methods.append(card.id)
            
            # Update payment setup
            payment_setup['payment_methods'] = current_payment_methods
            payment_setup['updated_at'] = datetime.utcnow().isoformat()

            # Save to database
            result = db_client.payment_container.replace_item(
                item=payment_setup['id'],
                body=payment_setup
            )

            return func.HttpResponse(
                json.dumps({
                    "status": "success",
                    "message": "Card added successfully",
                    "data": {
                        "payment_methods": result['payment_methods']
                    }
                }),
                mimetype="application/json",
                status_code=200
            )

        except stripe.error.CardError as e:
            logging.error(f'Card error: {str(e)}')
            return func.HttpResponse(
                json.dumps({
                    "error": e.error.message,
                    "error_code": e.error.code,
                    "decline_code": e.error.decline_code
                }),
                mimetype="application/json",
                status_code=400
            )

        except stripe.error.StripeError as e:
            logging.error(f'Stripe error: {str(e)}')
            return func.HttpResponse(
                json.dumps({
                    "error": "Failed to add card with Stripe",
                    "error_code": "stripe_error",
                    "details": str(e)
                }),
                mimetype="application/json",
                status_code=400
            )

    except Exception as e:
        logging.error(f'Error: {str(e)}')
        return func.HttpResponse(
            json.dumps({
                "error": "Server error",
                "error_code": "server_error",
                "details": str(e)
            }),
            mimetype="application/json",
            status_code=500
        )
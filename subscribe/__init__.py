import azure.functions as func
import json
import logging
import stripe
import os
from shared_code.db_client import CosmosDBClient
from shared_code.middleware import check_payment_access

stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

@check_payment_access
def main(req: func.HttpRequest) -> func.HttpResponse:
    db_client = CosmosDBClient()
    
    try:
        req_body = req.get_json()
        email = req_body.get('email')
        token = req_body.get('token')  # Stripe token from frontend

        if not all([email, token]):
            return func.HttpResponse(
                json.dumps({
                    "error": "Missing required fields",
                    "details": "Email and token are required"
                }),
                mimetype="application/json",
                status_code=400
            )

        # Get payment setup
        payment_setup = db_client.get_payment_setup(email)
        if not payment_setup:
            return func.HttpResponse(
                json.dumps({
                    "error": "Payment setup not found",
                    "details": "Please set up your payment method first"
                }),
                mimetype="application/json",
                status_code=404
            )

        if len(payment_setup.get('payment_methods', [])) >= 3:
            return func.HttpResponse(
                json.dumps({
                    "error": "Maximum cards reached",
                    "details": "You can only have up to 3 cards"
                }),
                mimetype="application/json",
                status_code=400
            )

        try:
            # Add card to customer
            card = stripe.Customer.create_source(
                payment_setup['stripe_customer_id'],
                source=token
            )

            # Update payment setup
            payment_methods = payment_setup.get('payment_methods', [])
            payment_methods.append(card.id)
            payment_setup['payment_methods'] = payment_methods
            payment_setup['updated_at'] = datetime.utcnow().isoformat()

            db_client.payment_container.replace_item(
                item=payment_setup['id'],
                body=payment_setup
            )

            return func.HttpResponse(
                json.dumps({
                    "status": "success",
                    "message": "Successfully added payment method",
                    "card_id": card.id
                }),
                mimetype="application/json",
                status_code=200
            )

        except stripe.error.CardError as e:
            error_msg = e.error.message
            logging.error(f"Card error: {error_msg}")
            return func.HttpResponse(
                json.dumps({
                    "error": "Card error",
                    "details": error_msg,
                    "error_code": e.error.code
                }),
                mimetype="application/json",
                status_code=400
            )

    except Exception as e:
        logging.error(f'Error adding payment method: {str(e)}')
        return func.HttpResponse(
            json.dumps({
                "error": "Server error",
                "details": str(e)
            }),
            mimetype="application/json",
            status_code=500
        )
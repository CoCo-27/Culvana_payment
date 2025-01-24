import azure.functions as func
import json
import logging
import stripe
import os
from shared_code.db_client import CosmosDBClient
from shared_code.middleware import check_payment_access
from datetime import datetime 

stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

@check_payment_access
def main(req: func.HttpRequest) -> func.HttpResponse:
    db_client = CosmosDBClient()
    
    try:
        req_body = req.get_json()
        email = req_body.get('email')
        card_id = req_body.get('cardId')

        if not all([email, card_id]):
            return func.HttpResponse(
                json.dumps({
                    "error": "Missing required fields",
                    "details": "Email and card_id are required"
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
                    "details": "Payment setup not found"
                }),
                mimetype="application/json",
                status_code=404
            )

        payment_methods = payment_setup.get('payment_methods', [])
        if card_id not in payment_methods:
            return func.HttpResponse(
                json.dumps({
                    "error": "Card not found",
                    "details": "This card is not associated with the account"
                }),
                mimetype="application/json",
                status_code=404
            )

        try:
            # Detach payment method instead of deleting source
            stripe.PaymentMethod.detach(card_id)

            # Update payment setup
            payment_methods.remove(card_id)
            payment_setup['payment_methods'] = payment_methods
            payment_setup['updated_at'] = datetime.utcnow().isoformat()

            db_client.payment_container.replace_item(
                item=payment_setup['id'],
                body=payment_setup
            )

            return func.HttpResponse(
                json.dumps({
                    "status": "success",
                    "message": "Successfully removed payment method"
                }),
                mimetype="application/json",
                status_code=200
            )

        except stripe.error.StripeError as e:
            error_msg = str(e)
            logging.error(f"Stripe error: {error_msg}")
            return func.HttpResponse(
                json.dumps({
                    "error": "Stripe error",
                    "details": error_msg
                }),
                mimetype="application/json",
                status_code=400
            )

    except Exception as e:
        logging.error(f'Error removing payment method: {str(e)}')
        return func.HttpResponse(
            json.dumps({
                "error": "Server error",
                "details": str(e)
            }),
            mimetype="application/json",
            status_code=500
        )
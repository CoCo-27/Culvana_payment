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
        payment_method_id = req_body.get('payment_method_id')
        
        if not all([email, payment_method_id]):
            return func.HttpResponse(
                json.dumps({
                    "error": "Email and payment method are required",
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

            # Attach payment method to customer using modern API
            payment_method = stripe.PaymentMethod.attach(
                payment_method_id,
                customer=payment_setup['stripe_customer_id']
            )

            # Update payment_methods array
            current_payment_methods = payment_setup.get('payment_methods', [])
            current_payment_methods.append(payment_method.id)
            
            # Update payment setup
            payment_setup['payment_methods'] = current_payment_methods
            payment_setup['updated_at'] = datetime.utcnow().isoformat()

            # Save to database
            result = db_client.payment_container.replace_item(
                item=payment_setup['id'],
                body=payment_setup
            )

            # Get card details for response
            card_details = {
                'id': payment_method.id,
                'brand': payment_method.card.brand,
                'last4': payment_method.card.last4,
                'exp_month': payment_method.card.exp_month,
                'exp_year': payment_method.card.exp_year
            }

            return func.HttpResponse(
                json.dumps({
                    "status": "success",
                    "message": "Card added successfully",
                    "data": {
                        "payment_method": card_details,
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
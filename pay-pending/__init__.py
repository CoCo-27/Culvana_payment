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
        payment_method_id = req_body.get('payment_method_id')

        if not all([email, payment_method_id]):
            return func.HttpResponse(
                json.dumps({
                    "error": "Missing required fields",
                    "details": "Email and payment method are required"
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

        pending_fee = payment_setup.get('pending_fee', 0)
        if pending_fee == 0:
            return func.HttpResponse(
                json.dumps({
                    "status": "success",
                    "message": "No pending fee to pay"
                }),
                mimetype="application/json",
                status_code=200
            )

        try:
            # Process payment
            payment_intent = stripe.PaymentIntent.create(
                amount=pending_fee,
                currency='usd',
                customer=payment_setup['stripe_customer_id'],
                payment_method=payment_method_id,
                off_session=True,
                confirm=True,
                description=f'Pending fee payment for {email}'
            )

            if payment_intent.status == 'succeeded':
                # Record transaction
                transaction = db_client.create_transaction(
                    user_id=email,
                    amount=pending_fee,
                    transaction_type="fee_payment",
                    status='completed',
                    stripe_session_id=payment_intent.id
                )

                # Update payment setup
                payment_setup['pending_fee'] = 0
                payment_setup['is_blocked'] = False
                payment_setup['updated_at'] = datetime.utcnow().isoformat()
                
                db_client.payment_container.replace_item(
                    item=payment_setup['id'],
                    body=payment_setup
                )

                return func.HttpResponse(
                    json.dumps({
                        "status": "success",
                        "message": "Successfully paid pending fee",
                        "transaction_id": payment_intent.id
                    }),
                    mimetype="application/json",
                    status_code=200
                )

        except stripe.error.CardError as e:
            error_msg = e.error.message
            logging.error(f"Card error: {error_msg}")
            return func.HttpResponse(
                json.dumps({
                    "error": "Payment failed",
                    "details": error_msg,
                    "error_code": e.error.code
                }),
                mimetype="application/json",
                status_code=400
            )

    except Exception as e:
        logging.error(f'Error processing payment: {str(e)}')
        return func.HttpResponse(
            json.dumps({
                "error": "Server error",
                "details": str(e)
            }),
            mimetype="application/json",
            status_code=500
        )
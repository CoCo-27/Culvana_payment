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
        logging.info(f"Request body: {req_body}")
        
        email = req_body.get('email')
        credit_amount = req_body.get('amount')
        try:
            credit_amount = int(credit_amount)
        except (TypeError, ValueError):
            return func.HttpResponse(
                json.dumps({
                    "error": "Invalid amount",
                    "details": "Credit amount must be a valid number"
                }),
                mimetype="application/json",
                
                status_code=400
            )
        if not email or not credit_amount:
            return func.HttpResponse(
                json.dumps({
                    "error": "Missing required fields",
                    "details": "Both email and amount are required"
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

        # Handle Stripe customer
        stripe_customer_id = payment_setup.get('stripe_customer_id')
        if not stripe_customer_id:
            try:
                customers = stripe.Customer.list(email=email, limit=1)
                if customers.data:
                    stripe_customer_id = customers.data[0].id
                else:
                    return func.HttpResponse(
                        json.dumps({
                            "error": "Payment method not found",
                            "details": "Please add a payment method to your account"
                        }),
                        mimetype="application/json",
                        status_code=400
                    )
            except stripe.error.StripeError as e:
                logging.error(f"Stripe customer lookup error: {str(e)}")
                return func.HttpResponse(
                    json.dumps({
                        "error": "Payment processing error",
                        "details": "Unable to retrieve payment information"
                    }),
                    mimetype="application/json",
                    status_code=400
                )

        try:
            # Process payment
            amount_in_cents = int(credit_amount) * 100
            charge = stripe.Charge.create(
                amount=amount_in_cents,
                currency='usd',
                customer=stripe_customer_id,
                description=f'Purchase of {credit_amount} credits',
                metadata={
                    'email': email,
                    'credit_amount': credit_amount,
                    'type': 'credit_purchase'
                }
            )

            if charge.status == 'succeeded':
                # Record transaction
                transaction = db_client.create_transaction(
                    user_id=email,
                    amount=amount_in_cents,
                    transaction_type="credit_purchase",
                    tokens=credit_amount,
                    status='completed',
                    stripe_session_id=charge.id
                )

                # Update credit balance
                current_balance = payment_setup.get('tokens', 0)
                new_balance = current_balance + credit_amount
                db_client.update_tokens(
                    email=email,
                    tokens=new_balance
                )

                return func.HttpResponse(
                    json.dumps({
                        "status": "success",
                        "message": f"Successfully purchased {credit_amount} credits",
                        "details": {
                            "previous_balance": current_balance,
                            "purchased_credits": credit_amount,
                            "new_balance": new_balance,
                            "transaction_id": charge.id
                        }
                    }),
                    mimetype="application/json",
                    status_code=200
                )
            else:
                raise stripe.error.CardError("Payment failed to process")

        except stripe.error.CardError as e:
            error_msg = e.error.message
            if e.error.code == 'insufficient_funds':
                error_msg = "Your card has insufficient funds. Please use a different card or try a smaller amount."
            elif e.error.code == 'card_declined':
                error_msg = "Your card was declined. Please use a different card or contact your bank."
            
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

        except stripe.error.StripeError as e:
            logging.error(f"Stripe error: {str(e)}")
            return func.HttpResponse(
                json.dumps({
                    "error": "Payment processing error",
                    "details": "Unable to process payment. Please try again."
                }),
                mimetype="application/json",
                status_code=400
            )

    except Exception as e:
        logging.error(f'Unexpected error: {str(e)}')
        return func.HttpResponse(
            json.dumps({
                "error": "Server error",
                "details": "An unexpected error occurred. Please try again later.",
                "error_code": "internal_error"
            }),
            mimetype="application/json",
            status_code=500
        )
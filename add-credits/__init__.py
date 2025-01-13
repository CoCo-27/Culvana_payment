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
        credit_amount = req_body.get('amount')  # Frontend sends dollar amount (e.g., 50 for $50.00)
        payment_method_id = req_body.get('payment_method_id')

        if not all([email, credit_amount]):
            return func.HttpResponse(
                json.dumps({
                    "error": "Missing required fields",
                    "details": "Email and amount are required"
                }),
                mimetype="application/json",
                status_code=400
            )

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

        if not payment_method_id:
            if not payment_setup.get('payment_methods') or not payment_setup['payment_methods']:
                return func.HttpResponse(
                    json.dumps({
                        "error": "No payment method found",
                        "details": "Please add a payment method first"
                    }),
                    mimetype="application/json",
                    status_code=400
                )
            payment_method_id = payment_setup['payment_methods'][0]
        else:
            if payment_method_id not in payment_setup.get('payment_methods', []):
                return func.HttpResponse(
                    json.dumps({
                        "error": "Invalid payment method",
                        "details": "The selected payment method does not belong to this account"
                    }),
                    mimetype="application/json",
                    status_code=400
                )

        try:
            # Convert dollar amount to cents for both Stripe and token storage
            amount_in_cents = credit_amount * 100  # 50 becomes 5000 cents
            
            # Create Stripe payment
            payment_intent = stripe.PaymentIntent.create(
                amount=amount_in_cents,  # Using cents (5000)
                currency='usd',
                customer=payment_setup['stripe_customer_id'],
                payment_method=payment_method_id,
                off_session=True,
                confirm=True,
                description=f'Purchase of ${credit_amount}.00 credits'  # Shows $50.00
            )

            if payment_intent.status == 'succeeded':
                # Create transaction record with cents amount
                transaction = db_client.create_transaction(
                    user_id=email,
                    amount=amount_in_cents,  # Storing 5000 cents
                    transaction_type="credit_purchase",
                    tokens=amount_in_cents,  # Storing 5000 cents
                    status='completed',
                    stripe_session_id=payment_intent.id
                )

                # Update token balance with cents
                current_balance = payment_setup.get('tokens', 0)  # Already in cents
                new_balance = current_balance + amount_in_cents  # Adding cents (5000)
                
                # Update the tokens in database
                db_client.update_tokens(
                    email=email,
                    tokens=new_balance  # Storing in cents
                )

                return func.HttpResponse(
                    json.dumps({
                        "status": "success",
                        "message": f"Successfully purchased ${credit_amount}.00 credits",
                        "details": {
                            "previous_balance": current_balance,  # In cents
                            "purchased_credits": amount_in_cents,  # In cents
                            "new_balance": new_balance,  # In cents
                            "transaction_id": payment_intent.id
                        }
                    }),
                    mimetype="application/json",
                    status_code=200
                )

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
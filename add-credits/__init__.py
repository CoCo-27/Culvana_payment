import azure.functions as func
import json
import logging
import stripe
import os
from shared_code.db_client import CosmosDBClient

db_client = CosmosDBClient()
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

async def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        req_body = req.get_json()
        email = req_body.get('email')
        credit_amount = req_body.get('amount')

        if not all([email, credit_amount]):
            return func.HttpResponse(
                json.dumps({"error": "Missing required fields"}),
                mimetype="application/json",
                status_code=400
            )

        # Get existing payment setup
        payment_setup = await db_client.get_payment_setup(email)
        if not payment_setup:
            return func.HttpResponse(
                json.dumps({"error": "No payment setup found for this email"}),
                mimetype="application/json",
                status_code=404
            )

        # Get or validate Stripe Customer
        stripe_customer_id = payment_setup.get('stripe_customer_id')
        if not stripe_customer_id:
            customers = stripe.Customer.list(email=email)
            if customers.data:
                customer = customers.data[0]
            else:
                return func.HttpResponse(
                    json.dumps({"error": "No payment method found"}),
                    mimetype="application/json",
                    status_code=400
                )
            stripe_customer_id = customer.id

        try:
            # Attempt the charge
            charge = stripe.Charge.create(
                amount=credit_amount * 100,  # Convert to cents
                currency='usd',
                customer=stripe_customer_id,
                description=f'Add {credit_amount} credits to account',
                metadata={
                    'email': email,
                    'credit_amount': credit_amount,
                    'type': 'add_credits'
                }
            )

            if charge.status == 'succeeded':
                # Create completed transaction record
                transaction = await db_client.create_transaction(
                    user_id=email,
                    amount=credit_amount * 100,
                    transaction_type="add_credits",
                    tokens=credit_amount,
                    status='completed',
                    stripe_session_id=charge.id
                )

                # Update payment setup with new token balance
                current_tokens = payment_setup.get('tokens', 0)
                new_balance = current_tokens + credit_amount
                await db_client.create_payment_setup(
                    email=email,
                    status='active',
                    tokens=new_balance
                )

                return func.HttpResponse(
                    json.dumps({
                        "status": "success",
                        "message": f"Successfully added {credit_amount} credits",
                        "new_balance": new_balance,
                        "charge_id": charge.id
                    }),
                    mimetype="application/json",
                    status_code=200
                )
            else:
                raise Exception('Payment failed')

        except stripe.error.CardError as e:
            error_message = e.error.message
            if e.error.code == 'insufficient_funds':
                error_message = "Insufficient funds available on your card. Please try a different card or a smaller amount."
            
            return func.HttpResponse(
                json.dumps({
                    "error": error_message,
                    "error_code": e.error.code
                }),
                mimetype="application/json",
                status_code=400
            )

    except Exception as e:
        logging.error(f'Error adding credits: {str(e)}')
        return func.HttpResponse(
            json.dumps({
                "error": "An unexpected error occurred. Please try again.",
                "error_code": "server_error"
            }),
            mimetype="application/json",
            status_code=500
        )
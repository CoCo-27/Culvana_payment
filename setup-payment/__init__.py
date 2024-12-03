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
        # Get request data
        req_body = req.get_json()
        email = req_body.get('email')
        location_name = req_body.get('location_name')
        location_address = req_body.get('location_address')
        token = req_body.get('token')
        
        if not all([email, location_name, location_address, token]):
            return func.HttpResponse(
                json.dumps({"error": "Missing required fields"}),
                mimetype="application/json",
                status_code=400
            )

        try:
            # Create or get Stripe Customer
            customers = stripe.Customer.list(email=email)
            if customers.data:
                customer = customers.data[0]
            else:
                customer = stripe.Customer.create(
                    email=email,
                    source=token
                )

            # Create charge
            charge = stripe.Charge.create(
                amount=4500,  # $45.00
                currency='usd',
                customer=customer.id,
                description=f'Setup fee including 20 tokens',
                metadata={
                    'email': email
                }
            )

            if charge.status == 'succeeded':
                # Create payment setup with tokens
                payment_setup = await db_client.create_payment_setup(
                    email=email,
                    status='active',
                    tokens=20
                )

                # Create location
                location = await db_client.create_location(
                    user_id=email,
                    name=location_name,
                    address=location_address
                )

                # Create completed transaction record
                transaction = await db_client.create_transaction(
                    user_id=email,
                    amount=4500,
                    transaction_type="setup",
                    location_id=location['id'],
                    tokens=20,
                    status='completed',
                    stripe_session_id=charge.id
                )

                return func.HttpResponse(
                    json.dumps({
                        'status': 'success',
                        'charge_id': charge.id,
                        'tokens_awarded': 20,
                        'current_balance': 20
                    }),
                    mimetype="application/json",
                    status_code=200
                )
            else:
                raise Exception('Payment failed')

        except stripe.error.CardError as e:
            logging.error(f'Card error: {str(e)}')
            return func.HttpResponse(
                json.dumps({
                    "error": e.error.message,
                    "error_code": "card_error"
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
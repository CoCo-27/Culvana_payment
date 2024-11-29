import azure.functions as func
import json
import logging
import stripe
import os
from datetime import datetime
from shared_code.db_client import CosmosDBClient
from shared_code.models import PaymentSetup, Transaction, Location, Plan, PlanType

db_client = CosmosDBClient()
app = func.FunctionApp()
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

# ... (previous imports remain the same)

@app.route(route="setup-payment", auth_level=func.AuthLevel.ANONYMOUS)
async def setup_payment(req: func.HttpRequest) -> func.HttpResponse:
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

        created_location_id = None
        try:

            # Create location
            location = await db_client.create_location(
                user_id=email,
                name=location_name,
                address=location_address
            )
            created_location_id = location['id']

            # Create initial transaction record
            transaction = await db_client.create_transaction(
                user_id=email,
                amount=Plan.INITIAL_SETUP_FEE,  # $45
                transaction_type="setup",
                location_id=location['id'],
                tokens=20  # Initial token amount
            )

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
                amount=Plan.INITIAL_SETUP_FEE,  # $45
                currency='usd',
                customer=customer.id,
                description=f'Setup fee including 20 tokens',
                metadata={
                    'email': email,
                    'location_id': location['id'],
                    'transaction_id': transaction['id']
                }
            )

            if charge.status == 'succeeded':
                # Update transaction to completed
                await db_client.create_transaction(
                    user_id=email,
                    amount=Plan.INITIAL_SETUP_FEE,
                    transaction_type="setup",
                    location_id=location['id'],
                    tokens=20,
                    status='completed',
                    stripe_session_id=charge.id
                )

                # Update payment setup with tokens and active status
                await db_client.create_payment_setup(
                    email=email,
                    status='active',
                    tokens=20  # Explicitly set 20 tokens
                )

                return func.HttpResponse(
                    json.dumps({
                        'status': 'success',
                        'charge_id': charge.id,
                        'tokens_awarded': 20,
                        'redirect_url': 'https://your-domain.com/payment/success'
                    }),
                    mimetype="application/json",
                    status_code=200
                )
            else:
                raise Exception('Payment failed')

        except stripe.error.CardError as e:
            logging.error(f'Card error: {str(e)}')
            await db_client.cleanup_failed_setup(email, created_location_id)
            return func.HttpResponse(
                json.dumps({
                    "error": e.error.message,
                    "redirect_url": 'https://your-domain.com/payment/failed'
                }),
                mimetype="application/json",
                status_code=400
            )

        except Exception as e:
            logging.error(f'Server error: {str(e)}')
            await db_client.cleanup_failed_setup(email, created_location_id)
            return func.HttpResponse(
                json.dumps({
                    "error": "Payment processing failed",
                    "redirect_url": 'https://your-domain.com/payment/failed'
                }),
                mimetype="application/json",
                status_code=500
            )

    except Exception as e:
        logging.error(f'Request error: {str(e)}')
        return func.HttpResponse(
            json.dumps({"error": "Invalid request"}),
            mimetype="application/json",
            status_code=400
        )

@app.route(route="payment-success", auth_level=func.AuthLevel.ANONYMOUS)
async def payment_success(req: func.HttpRequest) -> func.HttpResponse:
    try:
        session_id = req.params.get('session_id')
        if not session_id:
            return func.HttpResponse(
                json.dumps({"error": "No session ID provided"}),
                mimetype="application/json",
                status_code=400
            )

        # Get Stripe session
        session = stripe.checkout.Session.retrieve(session_id)
        
        # Find and update transaction
        transaction = await db_client.get_by_type_and_id('transaction', session.metadata.transaction_id)
        if transaction and transaction['status'] == 'pending':
            # Update transaction
            await db_client.create_transaction(
                user_id=transaction['user_id'],
                amount=transaction['amount'],
                transaction_type=transaction['transaction_type'],
                location_id=transaction['location_id'],
                tokens=transaction['tokens_included'],
                status='completed',
                stripe_session_id=session_id
            )

            # Update payment setup
            if payment_setup := await db_client.get_payment_setup(session.metadata.email):
                await db_client.create_payment_setup(
                    email=payment_setup['email'],
                    status='active',
                    tokens=Plan.INITIAL_TOKEN_AMOUNT
                )

            return func.HttpResponse(
                json.dumps({"status": "success"}),
                mimetype="application/json",
                status_code=200
            )

        return func.HttpResponse(
            json.dumps({"status": "already_processed"}),
            mimetype="application/json",
            status_code=200
        )

    except Exception as e:
        logging.error(f'Error in payment success: {str(e)}')
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            mimetype="application/json",
            status_code=500
        )


@app.route(route="add-credits", auth_level=func.AuthLevel.ANONYMOUS)
async def add_credits(req: func.HttpRequest) -> func.HttpResponse:
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

        # Attempt the charge
        try:
            charge = stripe.Charge.create(
                amount=credit_amount * 100,
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
            # Handle specific card errors
            error_message = e.error.message
            if e.error.code == 'insufficient_funds':
                error_message = "Insufficient funds available on your card. Please try a different card or a smaller amount."
            elif e.error.code == 'card_declined':
                error_message = "Your card was declined. Please try a different card."
            elif e.error.code == 'expired_card':
                error_message = "Your card has expired. Please update your card information."
            
            return func.HttpResponse(
                json.dumps({
                    "error": error_message,
                    "error_code": e.error.code
                }),
                mimetype="application/json",
                status_code=400
            )

        except stripe.error.InvalidRequestError as e:
            return func.HttpResponse(
                json.dumps({
                    "error": "Invalid request. Please check your payment details.",
                    "error_code": "invalid_request"
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
    
@app.route(route="add-location", auth_level=func.AuthLevel.ANONYMOUS)
async def add_location(req: func.HttpRequest) -> func.HttpResponse:
    try:
        req_body = req.get_json()
        email = req_body.get('email')
        location_name = req_body.get('location_name')
        location_address = req_body.get('location_address')
        
        LOCATION_COST = 45  # Cost in credits

        if not all([email, location_name, location_address]):
            return func.HttpResponse(
                json.dumps({"error": "Missing required fields"}),
                mimetype="application/json",
                status_code=400
            )

        # Get existing payment setup to check user's credits
        payment_setup = await db_client.get_payment_setup(email)
        if not payment_setup:
            return func.HttpResponse(
                json.dumps({"error": "No payment setup found for this email"}),
                mimetype="application/json",
                status_code=404
            )

        # Check if user has enough credits
        current_credits = payment_setup.get('tokens', 0)
        if current_credits < LOCATION_COST:
            return func.HttpResponse(
                json.dumps({
                    "error": f"Insufficient credits. You need {LOCATION_COST} credits but have {current_credits} credits.",
                    "error_code": "insufficient_credits"
                }),
                mimetype="application/json",
                status_code=400
            )

        # Create location
        location = await db_client.create_location(
            user_id=email,
            name=location_name,
            address=location_address
        )

        # Create transaction record
        transaction = await db_client.create_transaction(
            user_id=email,
            amount=LOCATION_COST * 100,  # Store in cents for consistency
            transaction_type="add_location",
            location_id=location['id'],
            tokens=-LOCATION_COST,  # Negative because we're spending credits
            status='completed'
        )

        # Update user's credit balance
        new_balance = current_credits - LOCATION_COST
        await db_client.create_payment_setup(
            email=email,
            status='active',
            tokens=new_balance
        )

        return func.HttpResponse(
            json.dumps({
                "status": "success",
                "message": f"Successfully added location: {location_name}",
                "location_id": location['id'],
                "remaining_credits": new_balance
            }),
            mimetype="application/json",
            status_code=200
        )

    except Exception as e:
        logging.error(f'Error adding location: {str(e)}')
        return func.HttpResponse(
            json.dumps({
                "error": "An unexpected error occurred. Please try again.",
                "error_code": "server_error"
            }),
            mimetype="application/json",
            status_code=500
        )
import azure.functions as func
import json
import logging
from shared_code.db_client import CosmosDBClient
from shared_code.models import PaymentSetup, Location, Transaction, Plan
import stripe
from shared_code.middleware import check_payment_access

async def main(req: func.HttpRequest) -> func.HttpResponse:
    db_client = CosmosDBClient()
    
    try:
        req_body = req.get_json()
        email = req_body.get('email')
        location_name = req_body.get('locationName')
        location_address = req_body.get('locationAddress')
        payment_method_id = req_body.get('payment_method_id')
        
        if not all([email, location_name, location_address, payment_method_id]):
            return func.HttpResponse(
                json.dumps({
                    "error": "Email, location name, location address, and payment method are required",
                    "error_code": "missing_fields"
                }),
                mimetype="application/json",
                status_code=400
            )

        try:
            customer = stripe.Customer.create(
                email=email
            )

            payment_method = stripe.PaymentMethod.attach(
                payment_method_id,
                customer=customer.id
            )

            stripe.Customer.modify(
                customer.id,
                invoice_settings={
                    'default_payment_method': payment_method.id
                }
            )

            payment_intent = stripe.PaymentIntent.create(
                amount=Plan.INITIAL_SETUP_FEE,
                currency='usd',
                customer=customer.id,
                payment_method=payment_method.id,
                off_session=True,
                confirm=True,
                description=f'Initial location setup for {email}'
            )

            payment_setup = PaymentSetup(
                email=email,
                status='active',
                tokens=Plan.INITIAL_REWARD,
                stripe_customer_id=customer.id,
                num_locations=1,
                pending_fee=0,
                monthly_usage=0,
                payment_methods=[payment_method.id]
            )

            location = Location(
                user_id=email,
                name=location_name,
                address=location_address
            )

            transaction = Transaction(
                user_id=email,
                amount=Plan.INITIAL_SETUP_FEE,
                transaction_type='setup',
                location_id=location.id,
                tokens=Plan.INITIAL_TOKEN_VALUE,
                status='completed',
                stripe_session_id=payment_intent.id
            )

            payment_result = db_client.payment_container.create_item(
                body=payment_setup.to_dict()
            )

            location_result = db_client.location_container.create_item(
                body=location.to_dict()
            )

            transaction_result = db_client.transaction_container.create_item(
                body=transaction.to_dict()
            )

            return func.HttpResponse(
                json.dumps({
                    "status": "success",
                    "message": "Payment setup and location creation completed successfully",
                    "data": {
                        "payment": {
                            "id": payment_result['id'],
                            "email": payment_result['email'],
                            "status": payment_result['status'],
                            "tokens": payment_result['tokens'],
                            "stripe_customer_id": payment_result['stripe_customer_id'],
                            "num_locations": payment_result['num_locations'],
                            "payment_methods": payment_result['payment_methods']
                        },
                        "location": {
                            "id": location_result['id'],
                            "name": location_result['name'],
                            "address": location_result['address'],
                            "is_active": location_result['is_active']
                        },
                        "transaction": {
                            "id": transaction_result['id'],
                            "amount": transaction_result['amount'],
                            "tokens": transaction_result['tokens_included'],
                            "status": transaction_result['status']
                        }
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
                    "error": "Failed to process payment with Stripe",
                    "error_code": "stripe_error",
                    "details": str(e)
                }),
                mimetype="application/json",
                status_code=400
            )

        except Exception as e:
            logging.error(f'Database error: {str(e)}')
            return func.HttpResponse(
                json.dumps({
                    "error": "Failed to setup payment and location",
                    "error_code": "database_error",
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
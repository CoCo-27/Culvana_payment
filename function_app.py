import azure.functions as func
import json
import logging
import stripe
import os
from datetime import datetime

app = func.FunctionApp()
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

@app.route(route="add-credits", auth_level=func.AuthLevel.ANONYMOUS)
def add_credits(req: func.HttpRequest) -> func.HttpResponse:
    try:
        req_body = req.get_json()
        user_id = req_body.get('user_id')
        amount = req_body.get('amount')
        success_url = req_body.get('success_url')
        cancel_url = req_body.get('cancel_url')

        if not all([user_id, amount, success_url, cancel_url]):
            return func.HttpResponse(
                json.dumps({"error": "Missing required fields"}),
                mimetype="application/json",
                status_code=400
            )

        amount_cents = int(float(amount) * 100)
        
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'unit_amount': amount_cents,
                    'product_data': {
                        'name': 'Additional Credits',
                        'description': 'One-time credit purchase',
                    },
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                'type': 'add_credits',
                'user_id': user_id,
                'amount': amount_cents
            }
        )

        return func.HttpResponse(
            json.dumps({
                'session_id': session.id,
                'url': session.url
            }),
            mimetype="application/json",
            status_code=200
        )
    except Exception as e:
        logging.error(f'Error in add credits: {str(e)}')
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            mimetype="application/json",
            status_code=500
        )
    
@app.route(route="setup-payment", auth_level=func.AuthLevel.ANONYMOUS)
def setup_payment(req: func.HttpRequest) -> func.HttpResponse:
    try:
        req_body = req.get_json()
        user_id = req_body.get('user_id')
        success_url = req_body.get('success_url')
        cancel_url = req_body.get('cancel_url')

        if not all([user_id, success_url, cancel_url]):
            return func.HttpResponse(
                json.dumps({"error": "Missing required fields"}),
                mimetype="application/json",
                status_code=400
            )

        # Create checkout session for initial setup ($35 + $10 token)
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'unit_amount': 3500,  # $35.00
                    'product_data': {
                        'name': 'Initial Setup',
                        'description': 'Setup fee including $10 initial tokens',
                    },
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                'type': 'initial_setup',
                'user_id': user_id,
                'includes_token': True,
                'token_amount': 1000  # $10.00 in tokens
            }
        )

        return func.HttpResponse(
            json.dumps({
                'session_id': session.id,
                'url': session.url
            }),
            mimetype="application/json",
            status_code=200
        )
    except Exception as e:
        logging.error(f'Error in setup payment: {str(e)}')
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            mimetype="application/json",
            status_code=500
        )

@app.route(route="add-location", auth_level=func.AuthLevel.ANONYMOUS)
def add_location(req: func.HttpRequest) -> func.HttpResponse:
    try:
        req_body = req.get_json()
        user_id = req_body.get('user_id')
        location_name = req_body.get('location_name')
        success_url = req_body.get('success_url')
        cancel_url = req_body.get('cancel_url')

        if not all([user_id, location_name, success_url, cancel_url]):
            return func.HttpResponse(
                json.dumps({"error": "Missing required fields"}),
                mimetype="application/json",
                status_code=400
            )

        # Create checkout session for new location ($35, no tokens)
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'unit_amount': 3500,  # $35.00
                    'product_data': {
                        'name': f'New Location: {location_name}',
                        'description': 'Location setup fee',
                    },
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                'type': 'new_location',
                'user_id': user_id,
                'location_name': location_name
            }
        )

        return func.HttpResponse(
            json.dumps({
                'session_id': session.id,
                'url': session.url
            }),
            mimetype="application/json",
            status_code=200
        )
    except Exception as e:
        logging.error(f'Error in add location: {str(e)}')
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            mimetype="application/json",
            status_code=500
        )
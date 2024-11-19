import azure.functions as func
import json
import logging
import stripe
import os
from datetime import datetime

stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

async def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        req_body = req.get_json()
        user_id = req_body.get('user_id')
        success_url = req_body.get('success_url')
        cancel_url = req_body.get('cancel_url')

        if not all([user_id, success_url, cancel_url]):
            return func.HttpResponse(
                json.dumps({"error": "Missing required fields"}),
                status_code=400
            )

        # Create checkout session for initial setup ($35 + $10 token)
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'unit_amount': 3500,
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
                'includes_token': True
            }
        )

        return func.HttpResponse(
            json.dumps({
                'session_id': session.id,
                'url': session.url
            }),
            status_code=200
        )

    except Exception as e:
        logging.error(f'Error in setup payment: {str(e)}')
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500
        )
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
        location_name = req_body.get('location_name')
        success_url = req_body.get('success_url')
        cancel_url = req_body.get('cancel_url')

        if not all([user_id, location_name, success_url, cancel_url]):
            return func.HttpResponse(
                json.dumps({"error": "Missing required fields"}),
                status_code=400
            )

        # Create checkout session for new location ($35, no tokens)
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'unit_amount': 3500,
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
            status_code=200
        )

    except Exception as e:
        logging.error(f'Error in add location: {str(e)}')
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500
        )
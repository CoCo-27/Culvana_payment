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
        amount = req_body.get('amount')  # Amount in dollars
        success_url = req_body.get('success_url')
        cancel_url = req_body.get('cancel_url')

        if not all([user_id, amount, success_url, cancel_url]):
            return func.HttpResponse(
                json.dumps({"error": "Missing required fields"}),
                status_code=400
            )

        # Convert amount to cents for Stripe
        amount_cents = int(float(amount) * 100)

        # Create checkout session for adding credits
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
            status_code=200
        )

    except Exception as e:
        logging.error(f'Error in add credits: {str(e)}')
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500
        )
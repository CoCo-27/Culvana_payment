import azure.functions as func
import json
import logging
import stripe
import os
from datetime import datetime
from shared_code.cosmos_client import CosmosClient

stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

async def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        # Verify webhook signature
        event = stripe.Webhook.construct_event(
            payload=req.get_body().decode(),
            sig_header=req.headers.get('stripe-signature'),
            secret=os.environ['STRIPE_WEBHOOK_SECRET']
        )

        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            cosmos_client = CosmosClient()

            if session.metadata.get('type') == 'initial_setup':
                # Create user setup with initial tokens
                await cosmos_client.create_payment_setup({
                    'user_id': session.metadata['user_id'],
                    'status': 'active',
                    'tokens': 1000,  # $10 initial tokens
                    'created_at': str(datetime.utcnow())
                })

            elif session.metadata.get('type') == 'new_location':
                # Create new location (no tokens)
                await cosmos_client.create_location({
                    'user_id': session.metadata['user_id'],
                    'name': session.metadata['location_name'],
                    'is_active': True,
                    'created_at': str(datetime.utcnow())
                })

            elif session.metadata.get('type') == 'add_credits':
                # Add one-time credits
                amount = int(session.metadata['amount'])
                await cosmos_client.add_credits(
                    session.metadata['user_id'],
                    amount
                )

        return func.HttpResponse(
            json.dumps({"status": "success"}),
            status_code=200
        )

    except stripe.error.SignatureVerificationError as e:
        logging.error(f'Webhook signature verification failed: {str(e)}')
        return func.HttpResponse(
            json.dumps({"error": "Invalid signature"}),
            status_code=400
        )
    except Exception as e:
        logging.error(f'Error processing webhook: {str(e)}')
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500
        )
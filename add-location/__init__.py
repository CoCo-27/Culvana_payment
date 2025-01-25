# add_location/__init__.py
import azure.functions as func
import json
import logging
from datetime import datetime, timezone
from shared_code.db_client import CosmosDBClient
from shared_code.middleware import check_payment_access
from shared_code.models import Plan

@check_payment_access
def main(req: func.HttpRequest) -> func.HttpResponse:
    db_client = CosmosDBClient()
    
    try:
        req_body = req.get_json()
        email = req_body.get('email')
        location_name = req_body.get('location_name')
        location_address = req_body.get('location_address')
        
        if not all([email, location_name, location_address]):
            return func.HttpResponse(
                json.dumps({
                    "error": "Missing required fields",
                    "details": {
                        "email": email,
                        "location_name": location_name,
                        "location_address": location_address
                    }
                }),
                mimetype="application/json",
                status_code=400
            )

        payment_setup = db_client.get_payment_setup(email)
        if not payment_setup:
            return func.HttpResponse(
                json.dumps({"error": "No payment setup found for this email"}),
                mimetype="application/json",
                status_code=404
            )

        current_credits = payment_setup.get('tokens', 0)
        current_num_locations = payment_setup.get('num_locations', 0)
        
        if current_credits < Plan.INITIAL_REWARD:
            return func.HttpResponse(
                json.dumps({
                    "error": f"Insufficient credits. You need {Plan.INITIAL_REWARD} credits but have {current_credits} credits.",
                    "error_code": "insufficient_credits"
                }),
                mimetype="application/json",
                status_code=400
            )

        current_time = datetime.now(timezone.utc).isoformat()

        location = db_client.create_location(
            user_id=email,
            name=location_name,
            address=location_address
        )

        transaction = db_client.create_transaction(
            user_id=email,
            amount=Plan.LOCATION_SETUP_FEE,
            transaction_type="add_location",
            location_id=location['id'],
            tokens=-Plan.INITIAL_REWARD,
            status='completed'
        )

        new_balance = current_credits - Plan.INITIAL_REWARD
        new_num_locations = current_num_locations + 1
        
        updated_setup = db_client.create_payment_setup(
            email=email,
            status=payment_setup.get('status', 'active'),
            tokens=new_balance,
            stripe_customer_id=payment_setup.get('stripe_customer_id'),
            plan_type=payment_setup.get('plan_type'),
            custom_threshold=payment_setup.get('custom_threshold'),
            num_locations=new_num_locations,
            pending_fee=payment_setup.get('pending_fee', 0)
        )

        logging.info(
            f"Added location for user {email}:"
            f"\n  Location ID: {location['id']}"
            f"\n  Name: {location_name}"
            f"\n  Credits used: {Plan.INITIAL_REWARD}"
            f"\n  New credit balance: {new_balance}"
            f"\n  Total locations: {new_num_locations}"
        )

        return func.HttpResponse(
            json.dumps({
                "status": "success",
                "message": f"Successfully added location: {location_name}",
                "data": {
                    "location": {
                        "id": location['id'],
                        "name": location_name,
                        "address": location_address,
                        "is_active": True,
                        "created_at": location['created_at']
                    },
                    "payment": {
                        "remaining_credits": new_balance,
                        "num_locations": new_num_locations,
                        "tokens_used": Plan.INITIAL_REWARD
                    },
                    "transaction_id": transaction['id']
                }
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
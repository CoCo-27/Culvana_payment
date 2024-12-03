import azure.functions as func
import json
import logging
from shared_code.db_client import CosmosDBClient

db_client = CosmosDBClient()

async def main(req: func.HttpRequest) -> func.HttpResponse:
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
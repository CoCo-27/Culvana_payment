import azure.functions as func
import json
import logging
from shared_code.db_client import CosmosDBClient
from shared_code.middleware import check_payment_access
from datetime import datetime 

@check_payment_access
def main(req: func.HttpRequest) -> func.HttpResponse:
    db_client = CosmosDBClient()
    
    try:
        req_body = req.get_json()
        email = req_body.get('email')

        if not email:
            return func.HttpResponse(
                json.dumps({
                    "error": "Missing required fields",
                    "details": "Email is required"
                }),
                mimetype="application/json",
                status_code=400
            )

        # Get payment setup
        payment_setup = db_client.get_payment_setup(email)
        if not payment_setup:
            return func.HttpResponse(
                json.dumps({
                    "error": "Payment setup not found",
                    "details": "Please set up your payment method first"
                }),
                mimetype="application/json",
                status_code=404
            )

        pending_fee = payment_setup.get('pending_fee', 0)
        current_tokens = payment_setup.get('tokens', 0)

        if pending_fee == 0:
            return func.HttpResponse(
                json.dumps({
                    "status": "success",
                    "message": "No pending fee to pay"
                }),
                mimetype="application/json",
                status_code=200
            )

        # Check if user has enough tokens
        if current_tokens < pending_fee:
            return func.HttpResponse(
                json.dumps({
                    "error": "Insufficient tokens",
                    "details": f"You need {pending_fee/100} tokens but have {current_tokens/100} tokens"
                }),
                mimetype="application/json",
                status_code=400
            )

        try:
            # Record transaction
            transaction = db_client.create_transaction(
                user_id=email,
                amount=pending_fee,
                transaction_type="fee_payment",
                status='completed',
                tokens=-pending_fee  # Deduct the pending fee amount from tokens
            )

            # Update payment setup
            new_token_balance = current_tokens - pending_fee
            payment_setup['tokens'] = new_token_balance
            payment_setup['pending_fee'] = 0
            payment_setup['is_blocked'] = False
            payment_setup['updated_at'] = datetime.utcnow().isoformat()
            
            db_client.payment_container.replace_item(
                item=payment_setup['id'],
                body=payment_setup
            )

            return func.HttpResponse(
                json.dumps({
                    "status": "success",
                    "message": "Successfully paid pending fee",
                    "data": {
                        "previous_balance": current_tokens,
                        "paid_amount": pending_fee,
                        "new_balance": new_token_balance,
                        "transaction_id": transaction['id']
                    }
                }),
                mimetype="application/json",
                status_code=200
            )

        except Exception as e:
            logging.error(f"Error processing fee payment: {str(e)}")
            return func.HttpResponse(
                json.dumps({
                    "error": "Payment processing failed",
                    "details": str(e)
                }),
                mimetype="application/json",
                status_code=400
            )

    except Exception as e:
        logging.error(f'Error processing payment: {str(e)}')
        return func.HttpResponse(
            json.dumps({
                "error": "Server error",
                "details": str(e)
            }),
            mimetype="application/json",
            status_code=500
        )
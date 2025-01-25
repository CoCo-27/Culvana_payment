# set_threshold/__init__.py
import azure.functions as func
import json
import logging
from shared_code.db_client import CosmosDBClient
from shared_code.models import PlanType, PLAN_THRESHOLDS
from shared_code.middleware import check_payment_access

@check_payment_access
def main(req: func.HttpRequest) -> func.HttpResponse:
    db_client = CosmosDBClient()
    
    try:
        req_body = req.get_json()
        email = req_body.get('email')
        plan_type = req_body.get('plan')
        custom_threshold = req_body.get('custom_threshold')

        if not email or not plan_type:
            return func.HttpResponse(
                json.dumps({"error": "Email and plan_type are required"}),
                mimetype="application/json",
                status_code=400
            )

        if plan_type not in [pt.value for pt in PlanType]:
            return func.HttpResponse(
                json.dumps({"error": "Invalid plan type"}),
                mimetype="application/json",
                status_code=400
            )

        if plan_type == PlanType.CUSTOM.value and not custom_threshold:
            return func.HttpResponse(
                json.dumps({"error": "Custom threshold is required for custom plan type"}),
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

        logging.info(f"Current payment setup: {payment_setup}")
        logging.info(f"Current num_locations: {payment_setup.get('num_locations', 0)}")

        if plan_type == PlanType.CUSTOM.value:
            threshold_amount = int(custom_threshold)
        else:
            threshold_amount = PLAN_THRESHOLDS.get(plan_type)

        logging.info(f"Plan type: {plan_type}, Threshold amount: {threshold_amount}")

        current_num_locations = payment_setup.get('num_locations', 0)
        current_pending_fee = payment_setup.get('pending_fee', 0)
        current_status = payment_setup.get('status', 'active')
        current_tokens = payment_setup.get('tokens', 0)
        current_stripe_customer_id = payment_setup.get('stripe_customer_id')
        current_payment_methods = payment_setup.get('payment_methods')
        current_monthly_usage = payment_setup.get('monthly_usage')

        logging.info(f"Updating with num_locations: {current_num_locations}")

        updated_setup = db_client.create_payment_setup(
            email=email,
            status=current_status,
            tokens=current_tokens,
            stripe_customer_id=current_stripe_customer_id,
            plan_type=plan_type,
            custom_threshold=int(custom_threshold) if plan_type == PlanType.CUSTOM.value else None,
            num_locations=current_num_locations,
            pending_fee=current_pending_fee,
            payment_methods = current_payment_methods, 
            monthly_usage = current_monthly_usage,
        )

        logging.info(f"Updated payment setup: {updated_setup}")

        return func.HttpResponse(
            json.dumps({
                "status": "success",
                "message": f"Successfully updated plan type and threshold for {email}",
                "plan_type": plan_type,
                "threshold": threshold_amount,
                "num_locations": current_num_locations,
                "updated_setup": updated_setup
            }),
            mimetype="application/json",
            status_code=200
        )

    except Exception as e:
        logging.error(f'Error setting threshold: {str(e)}')
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            mimetype="application/json",
            status_code=500
        )
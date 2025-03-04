import azure.functions as func
import json
import logging
from shared_code.db_client import CosmosDBClient
from datetime import datetime, timezone
from shared_code.middleware import check_payment_access

@check_payment_access
def main(req: func.HttpRequest) -> func.HttpResponse:
    db_client = CosmosDBClient()
    
    try:
        req_body = req.get_json()
        email = req_body.get('email')
        location_id = req_body.get('id')
        
        if not all([email, location_id]):
            return func.HttpResponse(
                json.dumps({
                    "error": "Missing required fields",
                    "error_code": "missing_fields"
                }),
                mimetype="application/json",
                status_code=400
            )

        try:
            payment_setup = db_client.get_payment_setup(email)
            if not payment_setup:
                return func.HttpResponse(
                    json.dumps({
                        "error": "No payment setup found for this email",
                        "error_code": "not_found"
                    }),
                    mimetype="application/json",
                    status_code=404
                )

            query = "SELECT * FROM c WHERE c.id = @location_id AND c.type = 'location' AND c.user_id = @user_id"
            parameters = [
                {"name": "@location_id", "value": location_id},
                {"name": "@user_id", "value": email}
            ]
            
            items = list(db_client.location_container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True
            ))

            if not items:
                return func.HttpResponse(
                    json.dumps({
                        "error": "Location not found or you don't have permission to update it",
                        "error_code": "not_found"
                    }),
                    mimetype="application/json",
                    status_code=404
                )

            existing_location = items[0]
            current_time = datetime.now(timezone.utc).isoformat()

            current_num_locations = payment_setup.get('num_locations', 0)
            if existing_location['is_active']:
                new_num_locations = max(0, current_num_locations - 1)
            else:
                new_num_locations = current_num_locations + 1

            payment_setup['num_locations'] = new_num_locations
            payment_setup['updated_at'] = current_time
            
            db_client.payment_container.replace_item(
                item=payment_setup['id'],
                body=payment_setup
            )

            existing_location['is_active'] = not existing_location['is_active']
            existing_location['updated_at'] = current_time
            
            if not existing_location['is_active']:
                existing_location['deactivated_at'] = current_time

            result = db_client.location_container.replace_item(
                item=existing_location['id'],
                body=existing_location
            )

            status_message = "deactivated" if not result['is_active'] else "activated"

            return func.HttpResponse(
                json.dumps({
                    "status": "success",
                    "message": f"Successfully {status_message} location: {result['name']}",
                    "data": {
                        "id": result['id'],
                        "name": result['name'],
                        "address": result['address'],
                        "is_active": result['is_active'],
                        "updated_at": result['updated_at'],
                        "num_locations": new_num_locations
                    }
                }),
                mimetype="application/json",
                status_code=200
            )

        except Exception as e:
            logging.error(f'Database error: {str(e)}')
            return func.HttpResponse(
                json.dumps({
                    "error": f"Failed to update location status: {str(e)}",
                    "error_code": "database_error"
                }),
                mimetype="application/json",
                status_code=400
            )

    except Exception as e:
        logging.error(f'Error: {str(e)}')
        return func.HttpResponse(
            json.dumps({
                "error": f"An unexpected error occurred: {str(e)}",
                "error_code": "server_error"
            }),
            mimetype="application/json",
            status_code=500
        )
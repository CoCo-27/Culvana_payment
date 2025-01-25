# update_location/__init__.py
import azure.functions as func
import json
import logging
from shared_code.db_client import CosmosDBClient
from datetime import datetime
from shared_code.middleware import check_payment_access

@check_payment_access
def main(req: func.HttpRequest) -> func.HttpResponse:
    db_client = CosmosDBClient()
    
    try:
        req_body = req.get_json()
        logging.info(f"Received request body: {req_body}")
        
        email = req_body.get('email')
        location_id = req_body.get('location_id')
        location_name = req_body.get('location_name')
        location_address = req_body.get('location_address')
        
        if not all([email, location_id, location_name, location_address]):
            return func.HttpResponse(
                json.dumps({
                    "error": "Missing required fields",
                    "error_code": "missing_fields",
                    "details": {
                        "email": email,
                        "location_id": location_id,
                        "location_name": location_name,
                        "location_address": location_address
                    }
                }),
                mimetype="application/json",
                status_code=400
            )

        try:
            payment_setup = db_client.get_payment_setup(email)
            if not payment_setup:
                return func.HttpResponse(
                    json.dumps({"error": "No payment setup found for this email"}),
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
            existing_location['name'] = location_name
            existing_location['address'] = location_address
            existing_location['updated_at'] = datetime.utcnow().isoformat()

            result = db_client.location_container.replace_item(
                item=existing_location['id'],
                body=existing_location
            )

            return func.HttpResponse(
                json.dumps({
                    "status": "success",
                    "message": f"Successfully updated location: {location_name}",
                    "data": {
                        "id": result['id'],
                        "name": result['name'],
                        "address": result['address'],
                        "is_active": result['is_active'],
                        "updated_at": result['updated_at']
                    }
                }),
                mimetype="application/json",
                status_code=200
            )

        except Exception as e:
            logging.error(f'Database error: {str(e)}')
            return func.HttpResponse(
                json.dumps({
                    "error": "Failed to update location",
                    "error_code": "database_error"
                }),
                mimetype="application/json",
                status_code=400
            )

    except Exception as e:
        logging.error(f'Error: {str(e)}')
        return func.HttpResponse(
            json.dumps({
                "error": "An unexpected error occurred. Please try again.",
                "error_code": "server_error"
            }),
            mimetype="application/json",
            status_code=500
        )
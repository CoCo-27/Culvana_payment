import azure.functions as func
import json
import logging
from shared_code.db_client import CosmosDBClient
from shared_code.middleware import check_payment_access
from datetime import datetime, timezone

@check_payment_access
def main(req: func.HttpRequest) -> func.HttpResponse:
    db_client = CosmosDBClient()
    
    try:
        req_body = req.get_json()
        email = req_body.get('email')
        location_id = req_body.get('location_id')
        
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
                        "error": "Location not found or you don't have permission to delete it",
                        "error_code": "not_found"
                    }),
                    mimetype="application/json",
                    status_code=404
                )

            existing_location = items[0]
            current_time = datetime.now(timezone.utc).isoformat()

            if existing_location['is_active']:
                current_num_locations = payment_setup.get('num_locations', 0)
                new_num_locations = max(0, current_num_locations - 1)
                
                payment_setup['num_locations'] = new_num_locations
                payment_setup['updated_at'] = current_time
                
                db_client.payment_container.replace_item(
                    item=payment_setup['id'],
                    body=payment_setup
                )
            
            try:
                db_client.location_container.delete_item(
                    item=existing_location['id'],
                    partition_key=existing_location['user_id']
                )

                return func.HttpResponse(
                    json.dumps({
                        "status": "success",
                        "message": f"Successfully deleted location: {existing_location['name']}",
                        "data": {
                            "id": existing_location['id'],
                            "name": existing_location['name'],
                            "was_active": existing_location['is_active'],
                            "num_locations": new_num_locations if existing_location['is_active'] else payment_setup['num_locations']
                        }
                    }),
                    mimetype="application/json",
                    status_code=200
                )
            except Exception as delete_error:
                logging.error(f"Delete operation error with user_id partition key: {str(delete_error)}")
                try:
                    db_client.location_container.delete_item(
                        item=existing_location['id'],
                        partition_key=existing_location['type']
                    )
                    
                    return func.HttpResponse(
                        json.dumps({
                            "status": "success",
                            "message": f"Successfully deleted location: {existing_location['name']}",
                            "data": {
                                "id": existing_location['id'],
                                "name": existing_location['name'],
                                "was_active": existing_location['is_active'],
                                "num_locations": new_num_locations if existing_location['is_active'] else payment_setup['num_locations']
                            }
                        }),
                        mimetype="application/json",
                        status_code=200
                    )
                except Exception as e:
                    raise Exception(f"Failed both deletion attempts: {str(e)}")

        except Exception as e:
            logging.error(f'Database error: {str(e)}')
            return func.HttpResponse(
                json.dumps({
                    "error": f"Failed to delete location: {str(e)}",
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
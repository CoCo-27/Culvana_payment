import azure.functions as func
import json
import logging
from shared_code.db_client import CosmosDBClient
from shared_code.middleware import check_payment_access
from datetime import datetime, timezone

def calculate_document_fee(pages: int) -> float:
    """Calculate fee for document processing"""
    return 20 * float(pages)

@check_payment_access
def main(req: func.HttpRequest) -> func.HttpResponse:
    db_client = CosmosDBClient()
    
    try:
        req_body = req.get_json()
        email = req_body.get('email')
        pages = req_body.get('pages')
        
        if not all([email, pages]):
            return func.HttpResponse(
                json.dumps({
                    "error": "Missing required fields",
                    "error_code": "missing_fields"
                }),
                mimetype="application/json",
                status_code=400
            )

        try:
            # Get user payment document
            query = f"SELECT * FROM c WHERE c.id = 'payment_{email}'"
            items = list(db_client.payment_container.query_items(
                query=query,
                enable_cross_partition_query=True
            ))

            if not items:
                return func.HttpResponse(
                    json.dumps({
                        "error": "User payment record not found",
                        "error_code": "user_not_found"
                    }),
                    mimetype="application/json",
                    status_code=404
                )

            payment_doc = items[0]
            
            # Calculate document fee
            fee = calculate_document_fee(pages)
            
            # Update pending fee
            payment_doc['pending_fee'] = payment_doc.get('pending_fee', 0) + fee
            payment_doc['updated_at'] = datetime.now(timezone.utc).isoformat()
            
            # Update payment document in database
            db_client.payment_container.replace_item(
                item=payment_doc['id'],
                body=payment_doc
            )

            return func.HttpResponse(
                json.dumps({
                    "status": "success",
                    "pending_fee": payment_doc['pending_fee'],
                    "added_fee": fee
                }),
                mimetype="application/json",
                status_code=200
            )

        except Exception as e:
            logging.error(f'Database error: {str(e)}')
            return func.HttpResponse(
                json.dumps({
                    "error": f"Failed to update pending fee: {str(e)}",
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
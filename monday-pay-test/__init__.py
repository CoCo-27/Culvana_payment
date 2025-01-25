# __init__.py
import azure.functions as func
import logging
from shared_code.db_client import CosmosDBClient
import asyncio
from datetime import datetime
import json

async def process_user_fee(db_client: CosmosDBClient, payment_setup):
    """Process pending fee deduction for a user"""
    logging.info(f"Processing payment for user: {payment_setup['user_id']}")
    
    try:
        tokens = payment_setup.get('tokens', 0)
        pending_fee = payment_setup.get('pending_fee', 0)
        
        result = {
            "user_id": payment_setup['user_id'],
            "processed_at": datetime.utcnow().isoformat(),
            "initial_tokens": tokens,
            "pending_fee": pending_fee,
            "success": False,
            "is_blocked": False,
            "message": ""
        }
        
        if pending_fee == 0:
            result.update({
                "success": True,
                "message": "No pending fee to process"
            })
            logging.info(f"No pending fee for user: {payment_setup['user_id']}")
            return result
            
        if tokens >= pending_fee:
            new_tokens = tokens - pending_fee
            
            payment_setup['tokens'] = new_tokens
            payment_setup['pending_fee'] = 0
            payment_setup['is_blocked'] = False
            payment_setup['updated_at'] = datetime.utcnow().isoformat()
            
            db_client.payment_container.replace_item(
                item=payment_setup['id'],
                body=payment_setup
            )
            
            result.update({
                "success": True,
                "final_tokens": new_tokens,
                "message": f"Successfully processed payment. Remaining tokens: {new_tokens}"
            })
            logging.info(f"Successfully processed payment for user: {payment_setup['user_id']}, remaining tokens: {new_tokens}")
            return result
        else:
            payment_setup['is_blocked'] = True
            payment_setup['updated_at'] = datetime.utcnow().isoformat()
            
            db_client.payment_container.replace_item(
                item=payment_setup['id'],
                body=payment_setup
            )
            
            result.update({
                "success": False,
                "is_blocked": True,
                "message": f"Insufficient tokens for payment. Required: {pending_fee}, Available: {tokens}"
            })
            logging.warning(f"Insufficient tokens for user: {payment_setup['user_id']}, required: {pending_fee}, available: {tokens}")
            return result
            
    except Exception as e:
        error_msg = f"Error processing payment for {payment_setup['user_id']}: {str(e)}"
        logging.error(error_msg)
        result.update({
            "success": False,
            "error": str(e),
            "message": "Internal error during payment processing"
        })
        return result

async def main(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP trigger function for testing payment processing"""
    logging.info('Payment processing test triggered via HTTP')
    
    try:
        db_client = CosmosDBClient()
        
        user_id = req.params.get('user_id')
        test_all = req.params.get('test_all', 'false').lower() == 'true'
        
        if test_all:
            query = """
            SELECT * FROM c 
            WHERE c.type = 'payment_setup' 
            AND c.pending_fee > 0
            """
        elif user_id:
            query = f"""
            SELECT * FROM c 
            WHERE c.type = 'payment_setup' 
            AND c.user_id = '{user_id}'
            """
        else:
            return func.HttpResponse(
                json.dumps({
                    "error": "Please provide user_id or set test_all=true"
                }),
                mimetype="application/json",
                status_code=400
            )
        
        payment_setups = list(db_client.payment_container.query_items(
            query=query,
            enable_cross_partition_query=True
        ))
        
        if not payment_setups:
            return func.HttpResponse(
                json.dumps({
                    "message": "No payments to process",
                    "user_id": user_id,
                    "test_all": test_all
                }),
                mimetype="application/json",
                status_code=200
            )
        
        results = await asyncio.gather(*[
            process_user_fee(db_client, payment_setup)
            for payment_setup in payment_setups
        ])
        
        summary = {
            "total_processed": len(results),
            "successful": sum(1 for r in results if r['success']),
            "blocked": sum(1 for r in results if r['is_blocked']),
            "details": results
        }
        
        return func.HttpResponse(
            json.dumps(summary),
            mimetype="application/json",
            status_code=200
        )
        
    except Exception as e:
        error_response = {
            "error": str(e),
            "message": "Internal server error during payment processing"
        }
        logging.error(f'Critical error in payment processing: {str(e)}')
        return func.HttpResponse(
            json.dumps(error_response),
            mimetype="application/json",
            status_code=500
        )

